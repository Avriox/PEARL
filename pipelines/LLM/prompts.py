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


def get_user_prompt(evidencepack: str) -> str:
    return f"""
You will receive an evidence pack with:
- All functions with static/dynamic metrics
- For each function, a prediction of whether it contains a bottleneck. This prediction is based on an embedding model which only has an accuracy of 64%. Above 0.5 indicates a tendency to contain bottlenecks, below 0.5 indicates a tendency to no bottleneck.
- Call tree and hot paths


Task:
1) From metrics and context only, either:
   - Inspect the individual functions, their characteristics and the call tree. 
   - Request code for specific functions (FQNs) you want to inspect. You cannot request code for [external] functions.
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


def get_source_code_prompt(code_bundle: Dict[str, str]) -> str:
    code_section = "\n\n".join(
        f"FQN: {fqn}\n--- CODE START ---\n{src}\n--- CODE END ---"
        for fqn, src in code_bundle.items()
    )
    return f"""
You are now given the source for specific functions you requested.

Task (inspection + repair stage):
1) Evaluate the provided functions against the profiling evidence. Not every requested function is necessarily problematic — be selective and precise.
2) If you need more context, request additional function sources by FQN.
3) If you identify a performance issue you can safely fix without changing the public API, include a complete replacement for that function directly in the bottlenecks list (replacement_source):
   - Same function name and exact signature (params, defaults, annotations).
   - Same input-output behavior and semantics (no API or behavior drift).
   - Keep or update the docstring if one exists.
   - The replacement must be a single valid Python function definition string. No Markdown fences or commentary.
   - Import any needed packages INSIDE the function so the replacement is self-contained.

Available packages you may assume are installed (import them inside the function if needed):
- threading, multiprocessing, concurrent.futures, asyncio
- numpy, pandas, numba, scipy, joblib
- functools (lru_cache), collections, itertools, heapq, bisect, array
- re, regex

Important constraints:
- Do not change function names, parameter lists, defaults, return types, or side effects unless already present and required for correctness.
- Maintain determinism and correctness. Avoid global state.
- If parallelizing, ensure it works when the function is imported and called in a standard Python environment (avoid patterns requiring top-level guards outside the function).
- Only include entries in bottlenecks if you also provide a safe, correct replacement_source for that function. Otherwise, request more code or set status="done".

Return strictly JSON matching this schema. No extra text:

{{
  "status": "continue" | "done",
  "code_requests": [{{"type":"function_source","fqn":"...","reason":"..."}}],
  "bottlenecks": [
    {{
      "fqn":"...",
      "bottleneck_type":"algorithmic_inefficiency" | "caching_memoization" | "object_churn" | "vectorization" | "io_batching" | "parallelization" | "inefficient_data_structure" | "repeated_regex_compile" | "other",
      "confidence":0.0,
      "issue_description":"...",
      "suggested_fix_summary":"...",
      "estimated_impact_percent":0.0,
      "replacement_source":"def ...:  # full, valid Python function definition; include any needed imports inside the function"
    }}
  ]
}}

Requested Function Sources:
{code_section}
"""
