PEARL 2.0 — Performance Evidence-Augmented Refactoring with LLMs
Complete, Implementation-Ready Architecture (with embedding-driven pattern matching and targeted exploration)

Overview and goals
- Objective: Build a one-click framework that profiles a Python project, identifies likely performance bottlenecks, lets an LLM explore the most promising functions (in a targeted, evidence-driven way), and recommends concrete fixes. Embedding-based retrieval of “bad” patterns and “good” fixes is supported but optional.
- Scope: Small to medium projects (tens to low hundreds of functions). Works in single-file mode or as a small package. All steps are described so you can implement them directly.
- Key ideas:
  - Performance fingerprints that blend static code features with dynamic telemetry.
  - Hot-path context: present top call paths, not just flat hot functions.
  - Data-flow hints: summarize argument sizes and value patterns (bridges metrics to “what the code does”).
  - Bottleneck hypothesis triage: the LLM ranks candidates and bottleneck types before requesting any code.
  - Optional pattern library + embeddings: nearest-neighbor matching against curated “before/after” antipattern examples; feed the LLM both the “bad” exemplar and the “good” fix alongside target code.
- Outcome: The LLM receives compact but rich evidence, asks for a handful of function sources, classifies issues, and proposes specific fixes. Optional: apply patches, re-run tests and profiling to verify gains.

High-level flow (one-click)
1) Initialization and ingest: discover files, parse ASTs, register functions.
2) Static analysis: compute complexity, loop structure, data-structure usage, and a static call graph.
3) Dynamic profiling: run workload/tests; collect function timing, line hotspots, memory, I/O, and argument repetition.
4) Fingerprints: fuse static and dynamic signals into standardized, per-function fingerprints.
5) Knowledge base:
   - Build a performance graph (dynamic call graph + node metrics).
   - Compute top execution hot paths (not just hot nodes).
   - Optional: build a pattern library and embedding indexes for examples and functions.
6) Triage:
   - Present fingerprints, hot paths, and dataflow hints to the LLM.
   - The LLM returns a ranked, structured list of “bottleneck hypotheses” (function → suspected type → confidence → evidence).
7) Targeted exploration:
   - For each hypothesis, assemble an evidence pack (code is added only when requested).
   - If using embeddings: attach nearest “bad” example(s) and corresponding “good” fix snippet(s).
8) Recommendation:
   - The LLM classifies the bottleneck, proposes a fix plan (transformation plan schema), and requests any additional code context if needed.
9) (Optional) Apply and validate:
   - Safely apply changes via AST/CST tools, run tests and benchmarks, accept/reject based on statistical criteria.
10) Log and iterate:
   - Store artifacts, prompts, decisions, and results; iterate until budget or improvement thresholds are met.

System prerequisites and modes
- Languages/OS: Python 3.11+; Linux preferred for reproducible CPU pinning; macOS acceptable with adjustments.
- Dependencies (minimal mode):
  - Parsing/metrics: ast, libcst or ast (for CST, pick one), radon (complexity), optionally astroid for better call resolution.
  - Profiling: cProfile or pyinstrument (function-level), line_profiler (line-level), tracemalloc (memory), optional: py-spy/scalene.
  - Storage: sqlite3 for registries; json/yaml for artifacts.
- Dependencies (enhanced mode):
  - Graph: networkx.
  - Embeddings: sentence-transformers (e5-base-v2/e5-large-v2) or OpenAI embeddings; vector DB (Chroma/FAISS).
  - Testing/bench: pytest, pyperf or pytest-benchmark.
- Single-file vs package:
  - Single-file: bundle the core pipeline; keep optional features behind flags. Use on-disk sqlite and JSON artifacts.
  - Package: split into modules (ingest, analysis, kb, tools, runner, eval); functionally identical.

Data model (central registry and artifacts)
- Function registry (SQLite table “functions”):
  - Keys: FQN (fully-qualified name), file_path, start_line, end_line, ast_hash (stable hash of AST without comments).
  - Signatures: signature text, docstring (first lines), decorators, imports.
  - Static features (JSON):
    - Cyclomatic complexity (CC), maintainability index (MI if used), loop count and max nesting depth.
    - Loop characteristics: comprehension usage, “membership tests in loops” flags, per-loop high-level summaries.
    - Data structure usage: counts of list/dict/set/tuple literals; membership operations; attribute lookups inside loops.
    - Concurrency hints: presence of threads/multiprocessing/async constructs.
    - External heavy calls: usage of numpy, pandas, re, database clients, HTTP.
  - Static callers/callees (FQN lists) and static call graph adjacency if available.
  - Fingerprint (JSON; completed after profiling).
- Dynamic metrics (SQLite “dynamic_metrics”):
  - For each run_id and function FQN:
    - Inclusive time (ms), exclusive time (ms), call_count, average per-call time (ms).
    - Line hotspots: list of hot lines with cumulative time and percent contribution; flag which are inside loops.
    - Memory: total allocated bytes attributed, peak memory in function scope if available; per-line allocation hotspots if aggregated from tracemalloc.
    - I/O: count and bytes per call site if instrumented.
    - Argument repetition: repetition_rate (fraction of calls with repeated arg signature), top repeated arg signatures (hashed keys).
- Performance graph (persisted as GraphML/JSON):
  - Nodes: FQNs with fingerprints and static/dynamic attributes.
  - Edges: caller → callee with total time contribution and call_count from dynamic profile.
- Pattern library (JSON/YAML; optional but recommended for embeddings):
  - Entries by pattern ID:
    - Name, detailed description of the antipattern and its detection signals.
    - Expected uplift range, known risks/constraints.
    - 3–10 “before” examples: small code snippets (or structured loop/operation descriptions) plus synthetic or real performance characteristics aligned with the pattern signals.
    - 1–3 “after” examples (paired fixes) with short explanations and constraints.

Stage 1 — Repository ingest and static analysis
1. Project discovery
- Traverse the project directory excluding virtualenv/build/migrations unless needed.
- Record all .py files, importable module paths, and main entry points.
- Optionally detect test framework by scanning for pytest/unittest markers.
- Build a manifest of files and modules.

2. AST parsing and chunk registration
- Parse each file into an AST (safe parse; fall back on error logging for broken files).
- Identify chunks:
  - FunctionChunk: top-level functions and class methods.
  - ClassChunk: class with method names/signatures (no method bodies unless needed).
  - ModuleChunk: selected modules for macro refactors.
- For each function/method:
  - Compute FQN as module.Class.function or module.function.
  - Record file_path and line range (start_line, end_line).
  - Extract signature string, docstring (first paragraph), decorators, and top-level imports.
  - Compute ast_hash to track code changes across versions.

3. Static feature extraction (per function)
- Complexity:
  - Cyclomatic complexity (CC): count decision nodes (if/elif/for/while/except/with/logical operators) + 1.
  - Maintainability Index (MI) optional: higher is better; helps prioritize low-risk refactors.
- Loop structure:
  - Count For/While loops; compute max nesting depth across nested loops and comprehensions.
  - Identify loop headers: patterns like range(N), enumerate, iterating over len(x), nested comprehensions.
  - Loop body operations: presence of membership checks (“in list”), repeated regex compilation, object allocations (list/dict/set creation).
- Data structures:
  - Count occurrences of list/dict/set/tuple constructs; identify membership checks on lists and sets; track conversions inside loops (list() calls, dict() construction).
- Concurrency indicators:
  - Presence of threading, multiprocessing, concurrent.futures, asyncio operations; use of synchronization primitives.
- External heavy calls:
  - Numpy/pandas usage; re.compile calls; database connectors; network requests; file I/O.
- Static call graph (best effort):
  - Resolve direct calls to known FQNs within the project; record static callers/callees (with low/high confidence flags when inference is uncertain).

Stage 2 — Dynamic profiling and telemetry
1. Environment control
- CPU pinning: pin to a fixed core set to reduce noise.
- Warm-up: run warm-up iterations before capturing timings (pyperf if used can self-calibrate).
- Record CPU frequency and system load if possible.

2. Function-level timing (baseline runs)
- Choose a profiler:
  - Sampling profiler (e.g., pyinstrument) for low overhead and accurate inclusive/exclusive timings with a clear call tree.
  - cProfile if line_profiler integration is essential; heavier overhead but standard.
- For each target workload or test suite run:
  - Capture per-function inclusive time, exclusive time, call counts.
  - Extract a dynamic call graph with edge weights equal to time attributed to callee when invoked by a caller (sum over all calls).

3. Line-level hotspots (targeted runs)
- Identify top-K hot functions by exclusive time or exclusive_time fraction ≥ threshold (e.g., 5% of total).
- For each, capture line-level timing:
  - Map hot lines to loop bodies and compute body-level cumulative time proportion.
  - Estimate per-iteration costs by dividing cumulative loop body time by estimated iteration counts if available.

4. Memory profiling
- Use tracemalloc snapshots around workload; attribute allocations to file:line.
- Aggregate to functions via line→FQN mapping:
  - For each function, record total allocation bytes across its contributing lines.
  - Identify lines inside loops that allocate frequently (object churn).
- Optional: record peak memory per function scope (approximate) by sampling during execution.

5. I/O profiling (optional but valuable)
- Instrument common I/O calls (file open/read/write, requests GET/POST, DB execute) to capture counts, bytes, and latency by call site.
- Attribute metrics back to calling functions via line→FQN mapping.

6. Argument-value profiling (cacheability signal)
- For the same top-K hot functions, wrap calls to record lightweight hashes of normalized arguments:
  - Normalize primitives by value; lists/tuples by prefix samples + length; numpy arrays by shape, dtype, and small data hash; dicts by key set and small sample.
- Compute repetition_rate as the fraction of calls where the arg signature repeats across the run.
- Cap the number of tracked calls to bound overhead (e.g., 50k).

7. Data-flow hints (augment fingerprints)
- Derive simple, high-signal hints per function from observed runs:
  - Typical input sizes and distributions (e.g., median and 90th percentile lengths of primary list arguments).
  - Constancy: functions whose outputs are the same across all calls after warm-up (e.g., get_config), signaling caching potential.
  - Input shape summaries (e.g., numpy shapes/dtypes or dict key sets).
  - Anomaly flags (e.g., repeatedly processing empty or tiny inputs many times).
- Persist these hints as part of the fingerprint for LLM consumption.

Stage 3 — Performance fingerprints (per function)
Every function receives a fingerprint JSON that fuses static features with dynamic evidence. Fields and computations:

1. Timing and ranking
- exclusive_time_ms and inclusive_time_ms: from the profiler.
- fraction_of_total_runtime: exclusive_time_ms divided by total program time across the run.
- call_count and average_time_ms: from profiling data.
- exclusive_vs_inclusive_ratio: exclusive_time_ms divided by inclusive_time_ms; values near 1 indicate time is spent locally rather than in callees.
- hot_path_rank: rank within top-N heaviest functions by exclusive_time fraction.

2. Loop characteristics
- static_loop_count and static_nested_depth: from AST analysis.
- dynamic_iteration_proxy: choose a representative line in a loop body; estimate iterations as (line execution count) divided by call_count.
- loop_body_hotness: percentage of exclusive time spent within loop bodies.

3. Data structure and operation signals
- membership_in_loop flag: presence of “in list” checks inside loops.
- data_structure_usage: counts of list/dict/set/tuple and conversions inside loops; flags for building dict/set per iteration.
- numeric_op_in_loop flag: simple arithmetic on numbers in loops (vectorization candidates).
- regex_compile_in_loop flag: re.compile or equivalent inside loop bodies.

4. Memory and I/O
- mem_alloc_bytes: total allocation bytes attributed to this function’s lines.
- allocation_hotspots: list of loop-body lines responsible for significant allocations and their contribution.
- io_operations and average_bytes_per_io: from I/O instrumentation if enabled.

5. Cacheability and purity
- arg_repetition_rate: from argument-value profiling.
- purity_assessment: heuristic over AST and imports:
  - no global/nonlocal writes,
  - no unguarded I/O,
  - return value structurally derived from inputs.
- cache_efficiency_score: function of repetition_rate and purity (for example, repetition_rate plus a bonus if pure, clipped to 0–1).

6. Parallelization score (0–1)
- Start baseline at 0.0 and add:
  - +0.3 if CPU-bound (CPU time close to wall time; low I/O fraction).
  - +0.2 if loop body writes only to local accumulators; no global/nonlocal/stateful mutations detected.
  - +0.2 if the loop is a map-like pattern (calling a pure function per element) or uses reductions (sum/min/max) safely.
  - +0.2 if inputs/outputs are numeric arrays or lists of primitives (vectorization or multi-core parallelization plausible).
- Subtract:
  - −0.3 for heavy object churn per iteration.
  - −0.2 for cross-iteration dependencies or shared mutable state access.
- Clip to [0, 1].

7. Data-flow hints (from Stage 2.7)
- Typical input size metrics (median/percentiles).
- Constancy flags (e.g., “returns same value after first call”).
- Shape/type summaries for arrays or structured inputs.

Stage 4 — Knowledge base and retrieval
4.1 Performance graph
- Build from the dynamic call graph with node attributes:
  - Attach each function’s fingerprint and static features.
  - Edge weights represent total time in callee attributable to a given caller.
- Hot path extraction:
  - Define a path as a sequence of caller→callee edges from entrypoint(s) down to leaves, following dynamic call tree instances.
  - Compute top K (e.g., 3–5) call paths by cumulative inclusive time along the path:
    - Aggregate inclusive time along the specific instance path (do not double-count a function if the path visits it once).
    - To avoid path explosion, consider the call tree from a sampling profiler or collapse recursive/self-cycles.
  - Store each hot path as a human-readable chain with cumulative time contribution percentage.

4.2 Pattern library (optional)
- Purpose: amplify LLM accuracy by retrieving relevant “before/after” examples and to guide fuzzy matching when function names are uninformative.
- Structure per pattern ID:
  - Name and long-form description of the antipattern.
  - Detection signals mapped to fingerprint fields (e.g., “arg_repetition_rate ≥ 0.3 and purity likely”).
  - Expected uplift range and risk notes (e.g., memory growth for caching).
  - Examples:
    - “Before” examples: 3–10 minimal code sketches (or structured loop/operation descriptions) each annotated with realistic performance characteristics that align with the detection signals (e.g., loop depth, membership checks, exclusive time fraction).
    - “After” examples: 1–3 minimal fixes that correspond to the “before” examples with a concise explanation of the applied transform and its constraints.
- Minimum viable library for small projects: 5–8 patterns (algorithmic inefficiency with membership in loops, caching/memoization, object churn, vectorization, I/O batching, repeated regex compile, inefficient data structure choice, unused parallelism).

4.3 Embeddings (optional but supported)
- Purpose: enable semantic similarity across:
  - Project functions (summaries) and pattern-library “before” examples.
  - Retrieve the best-matching “bad” example(s) and pair them with the corresponding “good” fixes for LLM prompts.
- What to embed:
  - Per function (document vector):
    - FQN and signature.
    - Docstring first lines if present.
    - Deterministic summary derived from fingerprint and static features:
      - Loop depth, loop hotness, membership_in_loop, regex_compile_in_loop, numeric_op_in_loop.
      - Exclusive/inclusive time and fraction of total, call_count, average per-call time.
      - Memory allocation signals and I/O summary.
      - Cacheability and parallelization scores.
      - Data-flow hints (typical input size, constancy flags).
    - Optionally a short, high-signal excerpt of code (e.g., the first lines or a loop sketch), but avoid very long code to keep vectors focused.
  - Per pattern “before” example (document vector):
    - Pattern ID and name.
    - Short description of the antipattern.
    - The “before” snippet’s loop/operation description (succinct).
    - The associated performance characteristics (aligned with fingerprint fields).
  - Per pattern “after” example (document vector, secondary):
    - Pattern ID and fix description (used primarily for retrieval into prompts after a match is found).
- Indexing:
  - Use a single collection with metadata fields for efficient filtering (e.g., exclusive_time fraction, loop_depth ≥ 2, membership flags, numpy present).
  - Persist embeddings and metadata with stable IDs linking back to functions or examples.
- Query strategy:
  - Triage retrieval:
    - For a given candidate (e.g., hot function with signals), form a query vector from its function-summary text.
    - Search the “before” example vectors within the corresponding pattern or across all patterns, after applying metadata filters that reflect the function’s fingerprint.
    - Select top-N “before” matches and bring along their paired “after” examples for the LLM.
  - Pattern-first retrieval:
    - For each pattern you want to check, form a query text from the pattern descriptor (or one of its “before” examples), filter project function vectors by metrics (e.g., exclusive_time ≥ threshold, loop_depth ≥ 2), and retrieve nearest functions.
- Example count guidance (for small projects):
  - Per pattern: 3–5 “before” examples is often enough for useful retrieval; 8–12 provides better coverage of variants.

Stage 5 — Triage and targeted exploration
5.1 Inputs presented to the LLM for triage
- Top K hot functions (e.g., 10–20) with compact fingerprint rows:
  - For each: FQN; exclusive_time fraction; exclusive_vs_inclusive ratio; call_count; loop_depth; membership_in_loop; regex_in_loop; numeric_op_in_loop; arg_repetition_rate; mem_alloc_bytes; io_ops; cache_efficiency_score; parallelization_score; key data-flow hints.
- Execution hot paths:
  - Present the top 3–5 call paths with a succinct chain (entry → … → leaf) and the cumulative time contribution. This shows where time is spent and suggests whether the real issue is a deep callee.
- Pattern-library candidates (if embeddings enabled):
  - For each hot function, optionally include top pattern matches with similarity scores and the names of matched patterns. Do not include code yet—only labels and high-level reasons.
- Constraints, budgets, and tools available:
  - Whether tests exist, whether numpy is available, whether concurrency is allowed, and what tools the LLM can call (see tools section below).

5.2 Bottleneck hypothesis triage (LLM output format)
- The LLM produces a ranked list of hypotheses, one per function candidate, each containing:
  - function_fqn.
  - hypothesized_bottleneck_type from a controlled set (e.g., Algorithmic Complexity, Caching/Memoization, Object Churn, Vectorization, I/O Batching, Parallelization, Inefficient Data Structure, Repeated Regex Compile).
  - confidence score in [0,1].
  - evidence summary grounded in fingerprint and hot-path context (e.g., “High exclusive time and nested loop depth of 2; hotspot lines fall inside inner loop; membership_in_loop flag true.”).
  - information requests: list of exact items needed next (e.g., “full source of function A,” “snippet of callee B’s loop,” “top callers with contribution,” “argument value histogram,” etc.).
- Controller behavior:
  - Select the top M hypotheses (e.g., 2–3) under budget.
  - For each, fulfill the requested information. When it includes source code, fetch from the function registry using file_path and line ranges.

5.3 Evidence pack assembly (per selected hypothesis)
Each evidence pack should be a compact, high-signal dossier:
- Target identification
  - FQN, module, class, signature.
- Performance summary
  - exclusive_time_ms, inclusive_time_ms, fraction_of_total_runtime, call_count, average per-call time, exclusive_vs_inclusive ratio, hot_path_rank.
- Bottleneck signals (aligned with patterns)
  - Loop characteristics: static counts and depth; dynamic iteration proxy; loop_body_hotness; membership_in_loop; numeric_op_in_loop; regex_compile_in_loop.
  - Cacheability: arg_repetition_rate, purity assessment, cache_efficiency_score.
  - Memory and I/O: mem_alloc_bytes; allocation hotspots in loop; io_operations and average bytes per call.
  - Parallelization score and reasons (e.g., independent iterations).
  - Data-flow hints: typical input sizes/shapes; constancy flags (e.g., function returns same value across calls after warm-up).
- Call context
  - Top callers with their contribution fractions to this function’s inclusive time.
  - Top callees with their share of the target’s inclusive time.
  - The top hot path(s) that include this function, showing the chain and cumulative contribution.
- Code context (on demand)
  - Full function body or trimmed version if large (include line numbers). Include only when requested by the LLM.
  - Optional: minimal snippets of immediately relevant callees if the LLM asks.
- Pattern matches (if embeddings enabled)
  - Matched “before” example(s): pattern ID, name, similarity score, and a prose description of the “bad” sketch and its performance traits.
  - Paired “after” example(s): fix sketch and explanation, constraints/risks, and expected uplift range.
- Constraints
  - Available dependencies (numpy, numba, multiprocessing viability).
  - Side-effect flags (I/O, database writes, randomness).
  - Test availability and coverage proxy (if measured).

5.4 Bottleneck-specific focus prompts (LLM tasking)
- Algorithmic complexity:
  - Goal: replace O(n²) idioms (e.g., membership checks in inner loops) with maps/sets, sort+two-pointer, binary search, heap, or divide-and-conquer approaches.
  - Success: lower per-call time; ideally reduced complexity evidenced by behavior across input sizes.
- Caching/memoization:
  - Goal: add bounded caches for pure or quasi-pure functions with high repetition; handle invalidation if needed.
  - Success: increased hit rates, reduced median latency per call, acceptable memory growth.
- Object churn/memory:
  - Goal: hoist allocations out of loops, reuse buffers, pre-allocate; reduce temporary object creation.
  - Success: lower allocation bytes in loops and improved time.
- Vectorization:
  - Goal: replace Python numeric loops with numpy operations or similar vectorized primitives.
  - Success: significant speedup with acceptable memory overhead.
- I/O batching:
  - Goal: batch small reads/writes, use buffered/async I/O where appropriate.
  - Success: reduced I/O calls and lower wall time.
- Parallelization:
  - Goal: exploit multi-core via multiprocessing/joblib for CPU-bound, independence-friendly loops; or asyncio for I/O-bound.
  - Success: speedup on multi-core without correctness issues.

Stage 6 — Tool interface for LLM (model-agnostic; no code returned here)
Provide fixed, auditable tools the LLM can call. Each tool returns structured data with clear fields:
- list_hotspots(filter):
  - Returns a ranked list of hot functions under a filter on fingerprint fields (e.g., min exclusive_time fraction, min loop depth).
  - Each entry includes the fingerprint summary row and links to callers/callees.
- get_function_code(fqn):
  - Returns the function’s full source, signature, docstring, file path, line range, ast_hash, and current fingerprint.
- get_callers(fqn, depth):
  - Returns callers up to the given depth, with contribution fractions and call counts.
- get_callees(fqn, depth):
  - Returns callees with contribution fractions and call counts.
- get_hot_paths(k):
  - Returns top K execution hot paths as sequences of FQNs with cumulative time contribution.
- get_performance_neighborhood(fqn, threshold):
  - Returns functions contributing more than threshold to the target’s runtime.
- find_pattern_matches(target):
  - If embeddings are enabled: returns top matching “before” examples (pattern ID, name, similarity, matched traits) and paired “after” examples.
  - If embeddings are disabled: returns rule-based matches based on fingerprint thresholds aligned with patterns.
- run_tests():
  - Runs the test suite; returns pass/fail and summary metrics.
- run_benchmarks(target):
  - Runs a micro-benchmark or end-to-end benchmark for a target; returns mean, variance, samples, and environment notes.
- propose_plan() / apply_plan() [optional in first release]:
  - LLM submits a transformation plan in a structured schema; the applier validates and applies changes on a branch; returns success/fail and diagnostics.

Stage 7 — Decision logic and iteration
7.1 Controller behavior
- Budgeting:
  - Cap number of LLM tool calls per hypothesis and total per run.
  - Cap number of source code fetches (e.g., request code only for top 2–3 hypotheses at a time).
- Selection:
  - Prefer leaf hotspots (high exclusive time) for simple local wins.
  - Also include at least one deep-leaf function in a top hot path to capture non-obvious core bottlenecks.
- Evidence delivery:
  - Always provide fingerprints and hot paths; include code only on request.
  - If embeddings are enabled, attach “bad/good” examples once a function is selected for inspection.
- Output expectation:
  - The LLM returns a bottleneck classification, rationale, and a concrete fix proposal (e.g., “precompute set of keys before loop; change membership checks to set; expected speedup 3–10x on N≥1e4; risk: memory overhead”).

7.2 Optional transformation and validation loop (later integration)
- Transformation plan schema (high-level):
  - reasoning narrative; expected impact (speedup, risk, interface changes);
  - a list of operations such as replace function body, add decorator, extract helper, add import, rename/move symbol, update call sites;
  - test requirements (e.g., existing tests pass, microbench improvement).
- Safe application:
  - Use CST/AST editing to locate and transform functions by FQN.
  - After edits: syntax check, static lint/type check if configured, run tests.
- Performance acceptance:
  - Benchmarks: calibrate with warm-up; collect multiple samples; compare baseline and candidate.
  - Statistical guardrails: accept only if speedup ≥ threshold (e.g., 10%) and a significance test passes; also guard memory regressions (e.g., ≤ 25% increase).

Stage 8 — Embedding-driven triage and example retrieval (if enabled)
8.1 Library curation and example design
- For each bottleneck type:
  - Prepare 3–10 “before” examples that concretely manifest the pattern. Keep them short but unambiguous. Annotate with fields parallel to fingerprint signals (e.g., loop depth=2; membership_in_loop=true; exclusive_time fraction “high”).
  - Prepare 1–3 paired “after” fixes that are idiomatic and safe; include a short prose reasoning and constraints (e.g., ordering semantics may change; cache size must be bounded).
- Document structure of examples:
  - Before example fields: title, description of operations, synthetic performance traits, possible inputs, constraints.
  - After example fields: transformed operations, rationale, risks, and expected uplift range.

8.2 Function and example embeddings
- Function summary composition for embedding:
  - FQN, signature, docstring (short).
  - Structured natural-language rendering of its fingerprint:
    - “Exclusive time is X% of total; called Y times; loop depth D; loop body hotness H%; membership checks inside loops present; regex compile inside loop absent; memory allocation bytes M; I/O operations N; argument repetition rate R; purity likely P; parallelization score S; typical input size ~Z.”
- Example summary composition (before/after):
  - Before: pattern name and narrative of the antipattern; loop/operation description; aligned perf traits.
  - After: fix narrative and constraints; expected uplift.
- Indexing and metadata:
  - For each document (function or example), store metadata fields for deterministic filtering: loop_depth, exclusive_time fraction category, membership flags, numeric_op flags, regex flags, arg_repetition category, numpy presence, etc.

8.3 Retrieval workflows
- Function-to-pattern matching:
  - For each hot function, run a filtered nearest-neighbor search against “before” examples:
    - Apply metadata filters derived from the function’s fingerprint.
    - Retrieve top matches by cosine similarity.
    - Attach top matches to the function’s evidence pack, along with their paired “after” fixes.
- Pattern-first scanning:
  - For a chosen bottleneck type (e.g., algorithmic), construct a query from the pattern’s descriptor.
  - Filter project functions by aligned metrics (e.g., exclusive_time ≥ threshold, loop_depth ≥ 2).
  - Retrieve top functions by similarity; surface them in triage even if their names are uninformative.

Stage 9 — Out-of-the-box guidance mechanisms integrated
9.1 Execution hot paths
- Include the top 3–5 hot call paths in every triage prompt. Each path lists:
  - The sequence of FQNs with indentation or arrows to show depth.
  - The cumulative time contribution of the path relative to the total run.
- Rationale:
  - Provides a narrative of where time is spent.
  - Helps the LLM focus on deep callees instead of surface-level coordinators.
- Implementation details:
  - Extract call tree from the dynamic profiler’s exported data.
  - Weight edges by callee time attributed under the caller.
  - Use a top-k path extraction on the call tree instances; if multiple identical subpaths exist, merge and report a representative path with cumulative share.

9.2 Data-flow augmentation
- Persist the following in fingerprints and surface in both triage and evidence packs:
  - Typical sizes of primary inputs (median, P90) and shape/dtype summaries for arrays.
  - Constancy flags for functions that consistently return the same value once warmed up.
  - Inferred invariants (e.g., keys of dict arguments stable across calls; many repeated values in certain args).
- Rationale:
  - Connects performance symptoms to operational reality (e.g., “processing 10,000 items in a loop with membership checks on a list”).

9.3 Bottleneck hypothesis triage prompt
- First LLM step is hypothesis generation, not code requests.
- Input to LLM:
  - Top hot functions’ fingerprint rows,
  - Top hot paths,
  - Any initial pattern matches (labels only),
  - Constraints/budgets.
- Required output from LLM per candidate:
  - FQN
  - hypothesized_bottleneck_type
  - confidence [0–1]
  - evidence (explicit references to fingerprint fields or hot-path facts)
  - information requests (what exact code or additional metrics are needed)
- Rationale:
  - Forces global reasoning over metrics before opening code, ensuring targeted exploration and reproducibility.

Stage 10 — Orchestration and user experience
10.1 One-click run
- Inputs required:
  - Project path, entrypoint command or test command, and optional thresholds (e.g., min exclusive_time fraction).
  - Whether embeddings and pattern library are enabled.
- Execution sequence:
  1) Ingest and static analysis.
  2) Profile and collect dynamic metrics.
  3) Build fingerprints and performance graph; compute hot paths.
  4) If enabled: load pattern library; build or load embeddings; index function summaries.
  5) Triage: present fingerprints, hot paths, initial matches; obtain hypotheses.
  6) For top hypotheses: assemble evidence packs; retrieve “before/after” examples if enabled; fetch code only on request.
  7) LLM returns recommendations and, optionally, a structured transformation plan.
  8) (Optional) Apply, test, benchmark, accept/reject; log outcomes.

10.2 Configuration and thresholds (defaults; make user-configurable)
- Hotspot selection:
  - Consider functions with exclusive_time fraction ≥ 5% or top 10–20 by exclusive time.
- Algorithmic suspicion:
  - Loop depth ≥ 2 or CC ≥ 10, with line hotspots inside inner loops.
- Cacheability:
  - arg_repetition_rate ≥ 0.3 and call_count ≥ 100, with purity likely.
- Parallelization candidates:
  - parallelization_score ≥ 0.6, CPU-bound, minimal shared state.
- Acceptance (if applying patches later):
  - Speedup ≥ 10% with statistical significance and memory increase ≤ 25%.

10.3 Artifacts and logging
- Persist every prompt and response, every tool call and its parameters, all fingerprints, hot paths, pattern matches, and evidence packs.
- Store per-run profiling artifacts and environment metadata for reproducibility.
- Keep change logs if transformation is enabled later (version graph with parent-child links and metrics).

What to implement now vs later
- Implement now (core):
  - Ingest, AST analysis, fingerprints, dynamic profiling, performance graph, hot paths.
  - Bottleneck hypothesis triage and targeted evidence packs.
  - If keeping it ultra-minimal: skip embeddings and pattern library; rely on fingerprint signals and hot paths for selection.
- Enable later (embedding-enhanced):
  - Pattern library with 3–10 “before” and 1–3 “after” examples per bottleneck type.
  - Function and pattern embeddings; retrieval to attach “bad” and “good” examples to evidence packs.
- Optional validation phase:
  - Transformation plan schema, AST/CST application, tests and benchmarks, acceptance criteria.

Implementation notes and calculation details (no code)
- Exclusive vs inclusive time:
  - Exclusive time of a function excludes time spent in callees; inclusive includes callees. The exclusive fraction is the strongest indicator of local optimization potential.
- Line hotspot attribution:
  - For line-profiler outputs, aggregate the cumulative time of lines within loop bodies and compute their share of the function’s exclusive time.
- Memory attribution:
  - From tracemalloc snapshots, map file:line to FQNs via registry line ranges; sum sizes; separate allocation hotspots inside loops.
- I/O metrics (if instrumented):
  - Count and sum bytes per file/network/database operation; record latency if available; attribute to FQNs by call site lines.
- Argument repetition normalization:
  - Produce a stable, truncated representation of args that preserves shape/type and small content samples; ensure constant-time hashing on typical sizes; cap total tracked calls per function.
- Purity assessment heuristic:
  - Flag I/O in body or callees; global/nonlocal writes; reliance on global configs; random seeds; network/database side effects; treat as “likely impure” unless proven safe.
- Parallelization score:
  - Apply additive score for independence and CPU-bound behavior, with penalties for shared state and heavy allocation churn.
- Hot path computation:
  - Use the profiler’s call tree instances to extract the heaviest root-to-leaf paths. Report the top 3–5 by cumulative inclusive time, with their percentage of total runtime. Avoid duplicate reporting of structurally identical subpaths—merge and report a representative with combined contribution.

How embeddings slot into your current idea
- Library examples:
  - Curate 3–10 “before” examples per bottleneck with a short, unambiguous description and aligned performance traits; author 1–3 “after” fixes with constraints and expected uplift range.
- Project matching:
  - Build a compact, semantic function summary for each project function by rendering its fingerprint in natural language; include FQN and signature to assist triangulation.
- Retrieval:
  - For a candidate function, find the nearest “before” examples after applying filters derived from the function’s fingerprint (e.g., membership_in_loop must be true to match AP-ALG-001).
  - Pair the retrieved “bad” example with its “good” fix and present both to the LLM alongside the target code in the evidence pack.
- Minimal example counts:
  - 3–5 “before” examples per pattern are often enough for small repos; expand to 8–12 for coverage of variants if you later go cross-project.

Why this architecture stays targeted
- The LLM never sees the entire code base at once. It reasons from metrics and hot paths, then asks for exactly the code it needs.
- The controller enforces a strict budget and only reveals code for top hypotheses.
- If embeddings are enabled, examples are retrieved per hypothesis, not globally; they serve as guardrails and accelerators, not as primary decision-makers.

Appendix — Bottleneck type catalog (example signals to implement)
- Algorithmic inefficiency (e.g., nested membership in loop)
  - Signals: high exclusive_time fraction; loop depth ≥ 2; membership_in_loop true; line hotspots concentrated in inner loop.
  - Fixes: replace list membership with set/dict precompute; sort+binary search; two-pointer scans; appropriate indexing.
- Caching/memoization
  - Signals: high call_count; arg_repetition_rate ≥ 0.3; purity likely; low I/O.
  - Fixes: bounded lru_cache; manual memo dict; memoize intermediate results across calls in the caller; cache invalidation and memory bounds required.
- Object churn (allocation-heavy)
  - Signals: mem_alloc_bytes high; allocation hotspots inside loops; repeated construction of lists/dicts or large temporaries.
  - Fixes: hoist allocations outside loops; reuse buffers; pre-size structures; prefer generators or views where appropriate.
- Vectorization
  - Signals: numeric_op_in_loop true; numpy imported or array-like inputs; CPU-bound profile; low I/O.
  - Fixes: numpy vector ops; broadcasting; consider numba (optional).
- I/O batching
  - Signals: high io_operations with small bytes per call; I/O time dominant; many repeated small requests.
  - Fixes: buffered I/O, chunking, bulk DB operations; async if latency-bound.
- Parallelization (CPU-bound, independent work)
  - Signals: parallelization_score ≥ 0.6; low shared state; map/reduce patterns; call_count high with similar-sized tasks.
  - Fixes: multiprocessing pools, joblib, concurrent.futures; careful with IPC and pickling.
- Repeated regex compile
  - Signals: regex_compile_in_loop true; line hotspots at compile sites; call_count high.
  - Fixes: precompile regex outside loops; cache compiled patterns keyed by pattern string.

What you can build next
- First pass (no embeddings):
  - Implement ingest → profiling → fingerprints → hot paths → hypothesis triage → targeted evidence packs → recommendations.
- Second pass (embedding-ready):
  - Add a minimal pattern library with 3–5 examples per pattern and their fixes.
  - Implement function/example embeddings with metadata filters and retrieval.
  - Enrich evidence packs with matched “bad” and “good” examples when a function is inspected.

This document is intentionally explicit about what to compute, store, and present at each stage so you can translate it directly into code. It maintains the targeted, metrics-first exploration you want while making the embedding/pattern library an optional accelerator you can add when you’re ready.