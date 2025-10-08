import json
import logging
import os
import uuid
from typing import Dict, List, Any, Optional, Callable
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

def check_api_key(model: str):
    provider = model.split("/", 1)[0] if "/" in model else "openai"
    env_name = PROVIDER_ENV.get(provider)
    if env_name is None:
        return
    if not os.getenv(env_name):
        raise RuntimeError(
            f"Missing API key for provider '{provider}'. Please set {env_name} in your .env"
        )

def _extract_payload(resp: Any) -> Dict[str, Any]:
    choice = resp["choices"][0]
    msg = choice.get("message", {}) or {}
    return msg

def _extract_text_or_tool_json(msg: Dict[str, Any]) -> str:
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
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()

def _coerce_json(s: str) -> Any:
    s = _strip_code_fences(s)
    try:
        return json.loads(s)
    except Exception:
        pass
    try:
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(s[start : end + 1])
    except Exception:
        pass
    raise ValueError("Could not parse JSON from model output")

def _insert_llm_event(db, payload: Dict[str, Any]):
    cols = ", ".join(payload.keys())
    placeholders = ", ".join(["?"] * len(payload))
    sql = f"INSERT INTO llm_interactions ({cols}) VALUES ({placeholders})"
    db.execute_write_sql(sql, tuple(payload.values()))

def _json_or_none(obj):
    try:
        return json.dumps(obj) if obj is not None else None
    except Exception:
        return None

def _has_fix_in_bottlenecks(bns: Any):
    """Return (has_any_fix, [fqns_with_fix])."""
    fqns = []
    if isinstance(bns, list):
        for b in bns:
            if not isinstance(b, dict):
                continue
            rs = b.get("replacement_source")
            if isinstance(rs, str) and rs.strip().startswith("def "):
                fqn = b.get("fqn")
                if fqn:
                    fqns.append(fqn)
    return (len(fqns) > 0, fqns)

class LLMClient():
    def __init__(
            self,
            model: str,
            db_path: str,
            project_id: str,
            temperature: float = 0.2,
            # NEW: hook that applies patches + re-profiles + returns fresh evidence
            reprofile_hook: Optional[
                Callable[[List[Dict[str, Any]], str, int, str], Dict[str, Any]]
            ] = None,
    ):
        self.model = model
        self.temperature = temperature
        self.project_id = project_id
        self.reprofile_hook = reprofile_hook

        check_api_key(model)
        self.db = ChunkDatabase(db_path)

    # NEW: always fetch latest version
    def _get_source_for_fqn(self, fqn: str) -> str:
        row = self.db.execute_sql(
            f"""
            SELECT source_code
            FROM functions
            WHERE fqn = '{fqn}' AND project_id = '{self.project_id}'
            ORDER BY version DESC
            LIMIT 1
            """
        )
        # execute_sql returns single value for 1x1
        return row

    def _handle_function_requests(self, requests: List[Dict[str, Any]]) -> str:
        code_bundle = {}
        failed_fqns = []

        for req in requests:
            if req.get("type") == "function_source" and req.get("fqn"):
                try:
                    code_bundle[req["fqn"]] = self._get_source_for_fqn(req["fqn"])
                    if code_bundle[req["fqn"]] is None:
                        failed_fqns.append(req["fqn"])
                except Exception:
                    failed_fqns.append(req["fqn"])

        if failed_fqns:
            return f"The following FQNs do not exist: {', '.join(failed_fqns)}. Please retry with valid FQNs."

        return get_source_code_prompt(code_bundle)

    def _send_request(self, messages: List[Dict[str, Any]], return_raw: bool = False):
        response = litellm.completion(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )
        msg = _extract_payload(response)
        text = _extract_text_or_tool_json(msg)
        usage = response.get("usage") or {}

        if return_raw:
            try:
                obj = _coerce_json(text)
            except Exception as e:
                raise RuntimeError(f"JSON_PARSE_ERROR::{text}") from e
            return obj, text, usage

        obj = _coerce_json(text)
        return obj

    # NEW: compute measured speedup using the latest two dynamic_runs
    def _log_post_reprofile(self, session_id: str, round_idx: int, run_id: Optional[str], patched_fqns: List[str]):
        rows = self.db.execute_sql(
            f"""
            SELECT run_id, total_time_ms
            FROM dynamic_runs
            WHERE project_id = '{self.project_id}'
            ORDER BY timestamp DESC
            LIMIT 2
            """
        )
        before_ms = None
        after_ms = None
        try:
            if isinstance(rows, list):
                if len(rows) >= 1:
                    after_ms = float(rows[0]["total_time_ms"])
                if len(rows) >= 2:
                    before_ms = float(rows[1]["total_time_ms"])
            elif isinstance(rows, dict):
                after_ms = float(rows["total_time_ms"])
        except Exception:
            pass

        speedup = None
        if before_ms and before_ms > 0 and after_ms is not None:
            speedup = max(before_ms - after_ms, 0.0) / before_ms * 100.0

        _insert_llm_event(self.db, {
            "session_id": session_id,
            "project_id": self.project_id,
            "llm_model": self.model,
            "round": round_idx,
            "stage": "post_reprofile",
            "event_type": "post_reprofile",
            "status": None,
            "meta_json": json.dumps({
                "patched_fqns": patched_fqns or [],
                "run_id": run_id,
                "measured_speedup_percent": speedup,
                "before_runtime_ms": before_ms,
                "after_runtime_ms": after_ms
            })
        })

    def optimize(self, profiling_evidence: str, max_rounds: int = 2):
        session_id = str(uuid.uuid4())
        current_stage = "triage"
        round_idx = 0

        messages: List[Dict[str, str]] = []
        messages.append({"role": "system", "content": SYSTEM_PROMPT})
        messages.append({"role": "user", "content": get_user_prompt(profiling_evidence)})

        repair_prompt = "Return only a valid JSON object that matches the schema for this step. No extra text."

        while round_idx < max_rounds:
            # Send request; log invalid JSON if needed
            try:
                response, raw_text, usage = self._send_request(messages, return_raw=True)
            except Exception as e1:
                raw_text = str(e1).split("JSON_PARSE_ERROR::", 1)[-1] if "JSON_PARSE_ERROR::" in str(e1) else ""
                _insert_llm_event(self.db, {
                    "session_id": session_id,
                    "project_id": self.project_id,
                    "llm_model": self.model,
                    "round": round_idx,
                    "stage": current_stage,
                    "event_type": "invalid_json",
                    "status": None,
                    "raw_model_output": raw_text,
                    "parsed_json": None,
                    "error_type": "invalid_json",
                    "error_message": repr(e1),
                })
                response, raw_text, usage = self._send_request(messages + [{"role": "user", "content": repair_prompt}], return_raw=True)

            # Log the successful response
            _insert_llm_event(self.db, {
                "session_id": session_id,
                "project_id": self.project_id,
                "llm_model": self.model,
                "round": round_idx,
                "stage": current_stage,
                "event_type": "response",
                "status": response.get("status"),
                "code_requests_json": _json_or_none(response.get("code_requests")),
                "hypotheses_json": _json_or_none(response.get("hypotheses")),
                "bottlenecks_json": _json_or_none(response.get("bottlenecks")),
                "raw_model_output": raw_text,
                "parsed_json": _json_or_none(response),
                "usage_prompt_tokens": (usage or {}).get("prompt_tokens"),
                "usage_completion_tokens": (usage or {}).get("completion_tokens"),
                "usage_total_tokens": (usage or {}).get("total_tokens"),
            })

            # If any bottleneck contains a replacement_source, mark as fix_submission and re-profile (via hook)
            has_fix, fix_fqns = _has_fix_in_bottlenecks(response.get("bottlenecks"))
            if has_fix:
                _insert_llm_event(self.db, {
                    "session_id": session_id,
                    "project_id": self.project_id,
                    "llm_model": self.model,
                    "round": round_idx,
                    "stage": current_stage,
                    "event_type": "fix_submission",
                    "status": response.get("status"),
                    "bottlenecks_json": _json_or_none(response.get("bottlenecks")),
                    "meta_json": json.dumps({"fix_fqns": fix_fqns}),
                })

                # Re-profile with patches and obtain updated evidence
                if self.reprofile_hook:
                    try:
                        reprof = self.reprofile_hook(response.get("bottlenecks") or [], session_id, round_idx, self.model)
                    except Exception as e:
                        reprof = {"ok": False, "error": f"reprofile_hook raised: {e}", "patched_fqns": fix_fqns}

                    if not reprof or not reprof.get("ok"):
                        _insert_llm_event(self.db, {
                            "session_id": session_id,
                            "project_id": self.project_id,
                            "llm_model": self.model,
                            "round": round_idx,
                            "stage": "repair",
                            "event_type": "fix_runtime_error",
                            "error_type": "runtime_error",
                            "error_message": (reprof or {}).get("error") or "patched run failed",
                            "meta_json": json.dumps({"patched_fqns": fix_fqns}),
                        })
                        # Continue the loop; the model may request different fixes next
                    else:
                        # Log post-reprofile metrics (optional; uses latest two runs)
                        self._log_post_reprofile(
                            session_id=session_id,
                            round_idx=round_idx,
                            run_id=reprof.get("run_id"),
                            patched_fqns=reprof.get("patched_fqns") or fix_fqns
                        )

                        # Reset conversation back to triage with updated evidence
                        new_ev = reprof.get("evidence")
                        if isinstance(new_ev, str) and new_ev.strip():
                            messages = [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": get_user_prompt(new_ev)},
                            ]
                            current_stage = "triage"

            if response.get("status") == "done":
                _insert_llm_event(self.db, {
                    "session_id": session_id,
                    "project_id": self.project_id,
                    "llm_model": self.model,
                    "round": round_idx,
                    "stage": current_stage,
                    "event_type": "status",
                    "status": "done",
                })
                return

            if response.get("status") == "continue" and response.get("code_requests"):
                _insert_llm_event(self.db, {
                    "session_id": session_id,
                    "project_id": self.project_id,
                    "llm_model": self.model,
                    "round": round_idx,
                    "stage": current_stage,
                    "event_type": "code_request",
                    "status": "continue",
                    "code_requests_json": _json_or_none(response.get("code_requests")),
                })

                function_response = self._handle_function_requests(response["code_requests"])

                if "do not exist" in function_response:
                    invalid = function_response.split(":", 1)[-1].split("Please")[0].strip()
                    invalid_list = [f.strip() for f in invalid.split(",") if f.strip()]
                    _insert_llm_event(self.db, {
                        "session_id": session_id,
                        "project_id": self.project_id,
                        "llm_model": self.model,
                        "round": round_idx,
                        "stage": current_stage,
                        "event_type": "invalid_fqn",
                        "invalid_fqns_json": _json_or_none(invalid_list),
                    })
                    messages.append({"role": "user", "content": function_response})
                    continue

                # Success: append code and bump round; switch to inspection
                messages.append({"role": "user", "content": function_response})
                round_idx += 1
                current_stage = "inspection"
            else:
                round_idx += 1