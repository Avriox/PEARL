import os
from typing import Any, Type, Dict, List

from dotenv import load_dotenv
import litellm
from instructor import from_litellm

# Load .env once so providers can pick up keys
load_dotenv()

# Provider -> env var name
PROVIDER_ENV: Dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "together": "TOGETHER_API_KEY",
}


def infer_provider(model: str) -> str:
    """
    Infer provider from model string prefix.
    Examples:
      openai/gpt-4o-mini -> openai
      anthropic/claude-3-5-sonnet-20240620 -> anthropic
      deepseek/deepseek-chat -> deepseek
      openrouter/meta-llama/Meta-Llama-3.1-70B-Instruct -> openrouter
    If no prefix is provided, default to 'openai'.
    """
    return model.split("/", 1)[0] if "/" in model else "openai"


def ensure_provider_api_key(model: str) -> None:
    provider = infer_provider(model)
    env_name = PROVIDER_ENV.get(provider)
    if env_name is None:
        # Unknown provider prefix - let LiteLLM handle or user set custom envs
        return
    if not os.getenv(env_name):
        raise RuntimeError(
            f"Missing API key for provider '{provider}'. Please set {env_name} in your .env"
        )


class LLMClient:
    """
    Thin wrapper around LiteLLM + Instructor for structured outputs.
    Correct usage: call chat.completions.create(..., response_model=...).
    """

    def __init__(self, model: str, temperature: float = 0.2):
        # Normalize model string (avoid leading/trailing spaces)
        self.model = (model or "").strip()
        self.temperature = temperature
        ensure_provider_api_key(self.model)

    def structured_chat(
        self, messages: List[Dict[str, str]], response_model: Type[Any]
    ):
        """
        Generic, provider-agnostic structured chat:
        - Calls litellm.completion (no Instructor)
        - Coaxes JSON-by-prompt; tries to parse tool-call arguments if present
        - 1 retry with a strict "JSON only" repair instruction if parsing fails
        - Validates with the provided Pydantic response_model
        """
        import json
        import re
        import litellm

        def _response_format_kwargs(model_name: str) -> Dict[str, Any]:
            # Prefer OpenAI json mode where supported; other providers will ignore safely.
            if infer_provider(model_name) == "openai":
                return {"response_format": {"type": "json_object"}}
            return {}

        def _extract_payload(resp: Any) -> Dict[str, Any]:
            # LiteLLM returns a dict-like object; unify extraction
            choice = resp["choices"][0]
            msg = choice.get("message", {}) or {}
            return msg

        def _extract_text_or_tool_json(msg: Dict[str, Any]) -> str:
            # If tool_calls exist with arguments, prefer that JSON; otherwise use content
            tool_calls = msg.get("tool_calls") or []
            if tool_calls:
                try:
                    fn = tool_calls[0].get("function", {}) or {}
                    args = fn.get("arguments")
                    if isinstance(args, (dict, list)):
                        return json.dumps(args)
                    if isinstance(args, str):
                        return args
                except Exception:
                    pass
            return msg.get("content") or ""

        def _strip_code_fences(s: str) -> str:
            s = s.strip()
            if s.startswith("```"):
                # Remove leading fences and any language hint
                s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
                # Remove trailing fences
                s = re.sub(r"\s*```$", "", s)
            return s.strip()

        def _coerce_json(s: str) -> Any:
            s = _strip_code_fences(s)
            # Try full string first
            try:
                return json.loads(s)
            except Exception:
                pass
            # Try to extract the largest {...} block
            try:
                start = s.find("{")
                end = s.rfind("}")
                if start != -1 and end != -1 and end > start:
                    return json.loads(s[start : end + 1])
            except Exception:
                pass
            raise ValueError("Could not parse JSON from model output")

        def _attempt(messages_: List[Dict[str, str]]):
            resp = litellm.completion(
                model=self.model,
                messages=messages_,
                temperature=self.temperature,
                **_response_format_kwargs(self.model),
            )
            msg = _extract_payload(resp)
            text = _extract_text_or_tool_json(msg)
            obj = _coerce_json(text)
            return response_model.model_validate(obj)

        # Attempt 1
        try:
            return _attempt(messages)
        except Exception as e1:
            # Attempt 2 (repair): append a strict JSON-only instruction
            repair = "Return only a valid JSON object that matches the schema for this step. No extra text."
            repaired_messages = messages + [{"role": "user", "content": repair}]
            try:
                return _attempt(repaired_messages)
            except Exception as e2:
                # Surface the last error with a hint
                raise RuntimeError(f"Failed to parse structured response: {e2}") from e1
