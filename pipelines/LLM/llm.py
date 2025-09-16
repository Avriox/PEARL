import json
import logging
import os
from typing import Dict, List, Any

import re

from dotenv import load_dotenv
import litellm

from pipelines.LLM.prompts import SYSTEM_PROMPT, get_user_prompt, get_source_code_prompt
from pipelines.code_analysis import ChunkDatabase

load_dotenv()

PROVIDER_ENV: Dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "together": "TOGETHER_API_KEY",
}

def check_api_key( model:str):
    provider = model.split("/", 1)[0] if "/" in model else "openai"
    env_name = PROVIDER_ENV.get(provider)
    if env_name is None:
        # Unknown provider prefix - let LiteLLM handle or user set custom envs
        return
    if not os.getenv(env_name):
        raise RuntimeError(
            f"Missing API key for provider '{provider}'. Please set {env_name} in your .env"
        )

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

class LLMClient():
    def __init__(self, model:str,db_path:str, project_id:str, temperature: float = 0.2):
        self.model = model
        self.temperature = temperature
        self.project_id = project_id

        check_api_key(model)
        self.db = ChunkDatabase(db_path)

    def _send_request(self, messages:List[Dict[str, Any]]):
        response = litellm.completion(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )

        msg = _extract_payload(response)
        text = _extract_text_or_tool_json(msg)
        obj = _coerce_json(text)
        return obj

    def _get_source_for_fqn(self, fqn: str) -> str:
        return self.db.execute_sql(f"SELECT source_code FROM functions WHERE fqn = '{fqn}' and project_id ='{self.project_id}'")

    def _handle_function_requests(self, requests: List[Dict[str, Any]]) -> str:
        code_bundle = {}
        failed_fqns = []

        for req in requests:
            if req.get("type") == "function_source" and req.get("fqn"):
                try:
                    code_bundle[req["fqn"]] = self._get_source_for_fqn(req["fqn"])
                except Exception:
                    failed_fqns.append(req["fqn"])

        if failed_fqns:
            return f"The following FQNs do not exist: {', '.join(failed_fqns)}. Please retry with valid FQNs."

        return get_source_code_prompt(code_bundle)

    def optimize(self, profiling_evidence:str, max_rounds: int = 2):
        messages: List[Dict[str, str]] = []

        # Add the system prompt to the messages list.
        messages.append({"role": "system", "content" : SYSTEM_PROMPT})

        # Append the user message including the evidence pack.
        messages.append({"role": "user", "content" : get_user_prompt(profiling_evidence)})

        logging.info(f"Sending request to LLM: {messages}")

        rounds = 0
        while rounds < max_rounds:
            try:
                response = self._send_request(messages)
            except Exception as e1:
                repair = "Return only a valid JSON object that matches the schema for this step. No extra text."
                try:
                    response = self._send_request(messages + [{"role": "user", "content": repair}])
                except Exception as e2:
                    raise RuntimeError(f"Failed to parse structured response: {e2}") from e1

            if response.get("status") == "done":
                return

            if response.get("status") == "continue" and response.get("code_requests"):
                function_response = self._handle_function_requests(response["code_requests"])
                messages.append({"role": "user", "content": function_response})

                # Only count successful function calls towards budget
                if "do not exist" not in function_response:
                    rounds += 1
            else:
                rounds += 1






