from typing import Dict

SYSTEM_PROMPT = """You are a performance triage assistant.

Your job:
- Read the provided profiling evidence (timings, fingerprints, call paths, docstrings, names).
- Decide which functions you want to inspect next and request source by FQN only when necessary.
- You may select targets based on any cues (metrics, names, call paths, docstrings) — not only runtime.
- Classify bottlenecks using this set:
  [algorithmic_inefficiency, caching_memoization, object_churn, vectorization, io_batching, parallelization, inefficient_data_structure, repeated_regex_compile, other].
- Always return strict JSON matching the schema for this step. No extra text.
- If you believe no meaningful opportunities remain at this granularity, return status="done".
- Use numeric estimated_impact_percent (0..100). Keep descriptions concise.
- Do not include freeform evidence sections or commentary outside the JSON.
"""


def triage_user_prompt(evidence_pack: str) -> str:
    return f"""
You will receive an evidence pack with:
- Project summary
- All functions with static/dynamic metrics
- Call tree and hot paths

Task (triage stage):
1) From metrics and context only, either:
   - Propose up to 3 prioritized hypotheses (optional), and/or
   - Request code for specific functions (FQNs) you want to inspect.
2) If requesting code, list FQNs and a short reason for each.
3) If nothing else is needed, set status="done".
4) Respond as JSON matching TriageReply:
{{
  "status": "continue" | "done",
  "code_requests": [{{"type":"function_source","fqn":"...","reason":"..."}}], 
  "hypotheses": [{{"fqn":"...","bottleneck_type":"...","confidence":0.0,"issue_description":"...","estimated_impact_percent": 0.0}}]
}}

Evidence Pack:
{evidence_pack}
"""


def inspection_user_prompt(evidence_pack: str, code_bundle: Dict[str, str]) -> str:
    code_section = "\n\n".join(
        f"FQN: {fqn}\n--- CODE START ---\n{src}\n--- CODE END ---"
        for fqn, src in code_bundle.items()
    )
    return f"""
You are now given the source for specific functions you requested.

Task (inspection stage):
1) Based on metrics and this code, return bottleneck findings (list).
2) If more code is needed, add code_requests with FQNs and reasons.
3) If nothing else is needed, set status="done".
4) Respond as JSON matching InspectionReply:
{{
  "status": "continue" | "done",
  "code_requests": [{{"type":"function_source","fqn":"...","reason":"..."}}],
  "bottlenecks": [
    {{
      "fqn":"...",
      "bottleneck_type":"...",
      "confidence":0.0,
      "issue_description":"...",
      "suggested_fix_summary":"...",
      "estimated_impact_percent": 0.0
    }}
  ]
}}

Evidence Pack (for reference):
{evidence_pack}

Requested Function Sources:
{code_section}
"""
