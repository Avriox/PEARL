from typing import Dict

def get_system_prompt(max_round):

    return f"""You are a performance triage assistant.

    Your job:
    - Read the provided profiling evidence (timings, fingerprints, call paths, docstrings, names).
    - Decide which functions you want to inspect next and request source by FQN only when necessary.
    - Request as much code as you need to get a detailed understanding of what the code does and how the functions interact.
    - You can only request code {max_round} times, but each time as many functions as needed to achieve your goal.
    - Avoid requesting the same function twice.
    - You may select targets based on any cues (metrics, names, call paths, docstrings, bottleneck prediction) — not only runtime.
    - Classify bottlenecks using this set:
      [algorithmic_inefficiency, caching_memoization, object_churn, vectorization, io_batching, parallelization, inefficient_data_structure, repeated_regex_compile, other].
    - Always return strict JSON matching the schema for this step. No extra text.
    - If you believe no meaningful opportunities remain at this granularity, return status="done".
    - Never rename any existing functions.
    - Use numeric estimated_impact to estimate overall runtime reduction in ms. Keep descriptions concise.
    - Do not include freeform evidence sections or commentary outside the JSON.

    """


def get_user_prompt(evidencepack: str, round_idx, max_round) -> str:
    return f"""
You will receive an evidence pack with:
- All functions with static/dynamic metrics
- For each function, a prediction of whether it contains a bottleneck. This prediction is based on an embedding model which only has an accuracy of 64%. Above 0.5 indicates a tendency to contain bottlenecks, below 0.5 indicates a tendency to no bottleneck, but the accuracy of this prediction is low.
- Call tree and hot paths
- This is round {round_idx+1} of {max_round} maximum rounds.


Task:
1) From metrics and context only:
   - Inspect the individual functions, their characteristics and the call tree. 
   - Request code for specific functions (FQNs) you want to inspect. You cannot request code for [external] functions.
2) If requesting code, list FQNs and a short reason for each.
3) If nothing else is needed, set status="done".
4) Respond as JSON matching TriageReply:
{{
  "status": "continue" | "done",
  "code_requests": [{{"type":"function_source","fqn":"...","reason":"..."}}], 
  "hypotheses": [{{"fqn":"...","bottleneck_type":"...","confidence":0.0,"issue_description":"...","estimated_impact": 0.0}}]
}}

Evidence Pack:
{evidencepack}
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
4) After providing code fixes, you will get updated profiling data including the new fixes in the next message. If you are certain there is no more work to do, set status="done" but you can also wait for the re-profiling results by continuing.
5) If after re-profiling you found a fix to not work or not be effective, do not include it in the bottlenecks list, otherwise always include all fixes you want to keep in the bottlenecks list.
6) Once you conclude the optimization to be done, the final message should contain all fixes you want to keep in the end in the bottlenecks list and the status should be set to done.

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
      "estimated_impact":0.0,
      "replacement_source":"def ...:  # full, valid Python function definition; include any needed imports inside the function"
    }}
  ]
}}

Requested Function Sources:
{code_section}
"""

def get_reprofile_user_prompt(evidencepack: str, round_idx: int, max_round: int) -> str:
    is_final = (round_idx >= max_round - 1)
    final_msg = "\n**THIS IS YOUR FINAL OPPORTUNITY** - Include all fixes you want to keep and set status='done'." if is_final else ""

    return f"""
Updated profiling evidence after applying your last fixes.

Continue the inspection + repair loop:
- If you need more context, request additional function sources by FQN only.
- If you propose a fix, include a full replacement_source for that function (same name/signature/behavior; imports inside the function; self-contained).
- Keep any fixes you still endorse by including them again in bottlenecks; omit ones you want to drop.
- Set status="done" when no meaningful opportunities remain.{final_msg}

Respond with STRICT JSON only (no extra text) using this schema:
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
      "estimated_impact":0.0,
      "replacement_source":"def ...  # full, valid Python function; include any needed imports inside the function"
    }}
  ]
}}

Round {round_idx+1} of {max_round}.

Evidence Pack:
{evidencepack}
"""