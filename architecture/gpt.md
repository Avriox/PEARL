Below is a full, implementation-ready blueprint for PEARL — Performance Evidence-Augmented Refactoring with LLMs. It turns the high-level ATLAS plan you liked into a complete engineering spec. I call out wherever something is inspired by SBLLM (iterative refinement/search and pattern retrieval) and add concrete, detailed steps for each phase, including data models, algorithms, libraries, heuristics, and operational practices.

Scope notes
- Audience: a single developer building a rigorous master-thesis system.
- Philosophy: pragmatic first, extendable later. Anything “crazy” is clearly marked optional.
- Novelty: performance fingerprints + evidence packs + bottleneck-specific pipelines + structured transformation plans + statistical acceptance criteria, all integrated with a standardized tool interface. Iterative refinement is inspired by SBLLM; all fingerprints/evidence packs/pipelines/DSL/version graph are new to this design.

0) System prerequisites and setup
- Languages: Python 3.11+ (for typing and perf improvements).
- OS: Linux recommended (reproducible perf via CPU pinning, taskset; macOS works too with some changes).
- Hardware: 8 CPU cores minimum; optional GPU not required.
- Python libs (install as needed):
  - Parsing/AST/CST: ast, astroid, libcst, radon, rope (or bowler).
  - Profiling: cProfile, pyinstrument OR py-spy, line-profiler, tracemalloc, (optional: scalene).
  - Stats/perf: pyperf, numpy, scipy.
  - Graphs/DB: networkx, sqlite3, (optional: Neo4j if you want external graph DB).
  - Vector DB: chromadb or FAISS; embeddings from sentence-transformers (e.g., e5-base-v2), or OpenAI embeddings if available.
  - Testing: pytest, hypothesis, pytest-benchmark or pyperf.
  - Orchestration: pydantic for schemas; gitpython for Git automation; psutil for CPU pinning.
  - LLM tool use: your chosen LLM SDKs (OpenAI, Anthropic, Google), or OpenRouter.

Folder structure (suggested)
- pearl/
  - config/
  - ingest/
  - analysis/  # static analysis + profiling + fingerprints
  - kb/        # vector DB + performance graph + bottleneck library
  - tools/     # LLM tool server or utilities
  - plans/     # transformation plan schemas + applier
  - runner/    # optimization loop
  - eval/      # metrics, statistical tests, reporting
  - data/
    - projects/<project_name>/  # working copy of repo
    - artifacts/<project_name>/  # profiles, fingerprints, graphs, versions
- scripts/   # CLI wrappers
- notebooks/ # optional analysis notebooks
- Makefile / tox.ini / pyproject.toml

1) Code analysis pipeline (initialization phase, step-by-step)

1.1 Repository ingestion
- Input: path to a Python project with tests/bench harness you control.
- Collect all .py files except:
  - Virtual env folders, build folders, migrations if irrelevant, tests (optional include tests).
- Maintain a manifest with file paths and module names (importable module path if package).

1.2 Parsing and chunking (function/class/module)
- Use ast and astroid:
  - ast to parse code safely and quickly into ASTs.
  - astroid to get richer semantic info (attribute access, inferred names).
- Build FQNs (fully-qualified names):
  - module.Class.method or module.function. Use module path from file location.
- Chunk types:
  - FunctionChunk: each top-level function or class method.
  - ClassChunk: a class with its method signatures (no bodies by default).
  - ModuleChunk: a whole module file for macro refactors.
- Extract per-chunk metadata:
  - file_path, line_range (start/end lineno), signature text (via ast.get_source_segment or inspect signatures), docstring (ast.get_docstring), decorators, imports (collect Import and ImportFrom nodes at module scope), called functions (static call targets via astroid resolution; fallback heuristics for dynamic calls).
- Store chunks in a SQLite “function registry”:
  - functions table: id (FQN), file_path, start_line, end_line, ast_hash, signature, decorators, docstring, imports, callers (list of FQNs), callees (list of FQNs), class_name (nullable), module_name, static_features JSON.
  - ast_hash: stable hash of AST (strip comments and whitespace): e.g., hash(ast.dump(node, include_attributes=False)).

1.3 Static analysis features
- Complexity metrics with radon:
  - Cyclomatic complexity (CC), maintainability index (MI).
- Loop structure:
  - Traverse AST to count For/While nodes, track nesting depth, presence of break/continue.
  - Collect loop headers (e.g., range(len(x)), nested comprehensions).
- Data structure usage:
  - For each function, count occurrences of list/dict/set/tuple literals, comprehensions, subscripts, attribute lookups inside loops.
- Concurrency primitives:
  - Scan imports and calls: threading.Thread, multiprocessing.Pool, asyncio.gather, concurrent.futures.
- External heavy calls:
  - Identify calls to numpy, pandas, re (regex), database drivers (psycopg2, sqlite3), requests/httpx.
- Store static features per function in registry (JSON column static_features).

1.4 Static call graph
- Using astroid, resolve Call nodes to potential function targets:
  - For direct function calls defined in the project, resolve to FQNs.
  - For methods: resolve class types if possible (astroid inference), else attach uncertain “possible targets” with a confidence score.
- Build a directed call graph G_static (networkx.DiGraph):
  - Nodes: function FQNs; Edges: caller -> callee with weight=1 (will reweight later with dynamic data).
- Save G_static to artifacts as graphml or pickle.

1.5 Chunk embeddings for RAG
- For each FunctionChunk:
  - Build textual representation for embedding:
    - Header: FQN + signature + docstring (first 2-3 lines).
    - Short summary: synthesize deterministically without LLM, e.g., “Calls: [a,b,c]; Uses: list,set; Loops: depth=2; CC=7”.
    - Optionally include first 20 lines of code; avoid whole body for large funcs (embedding cost).
- Choose embedding model:
  - Open-source: intfloat/e5-base-v2 or e5-large-v2 via sentence-transformers.
  - Or commercial: text-embedding-3-large for best quality, if allowed.
- Build a Vector DB:
  - ChromaDB (embedded, simple) or FAISS index on disk.
  - Store: vector, FQN, module, class, path, static_features.

2) Dynamic profiling and telemetry (initialization phase)

General design
- You’ll run the project’s entry points or tests to exercise functionality. Your planted bottlenecks must be covered. For each run, collect:
  - Function timing (inclusive/exclusive).
  - Line-level hotspots (top N).
  - Memory allocations.
  - I/O counts and bytes (optional).
- Run in controlled environment:
  - CPU pinning: taskset -c 0-3 or via psutil to pin process to a core set.
  - Disable frequency scaling (if possible) or record CPU frequency.
  - Warm up runs (pyperf calibrates automatically).

2.1 Function-level timing
- Baseline profiler: pyinstrument or cProfile.
  - pyinstrument: low overhead, great call tree; cProfile: standard, line_profiler integrates better.
- Suggested approach:
  - Use pyinstrument for call tree and inclusive/exclusive per function.
  - For top functions (by exclusive time), run line_profiler to get line breakdown.
- Collect dynamic call graph from pyinstrument:
  - Parse JSON export to extract caller->callee relationships with times and counts.

2.2 Line-level hotspots
- line_profiler:
  - Decorate target functions dynamically:
    - Strategy: after first pyinstrument run, take top-K hot functions (exclusive time ≥ threshold, e.g., 5% of total) and instrument them.
  - Collect per-line time; map to loop bodies (lines inside For/While).
- Heuristic: lines repeated inside loops with high cumulative time suggest inner-loop inefficiency.

2.3 Memory profiling
- tracemalloc:
  - Start/stop around workloads; take snapshots before/after and during (e.g., every N ms if you run a manual loop).
  - Map memory allocations to file:line; aggregate per function by mapping lines to FQN using registry spans.
- Optional: scalene for CPU vs memory fraction per line/function (more complex; useful but optional).

2.4 I/O profiling (optional but valuable)
- Monkey-patch common I/O calls for metrics:
  - open, pathlib.Path.open; requests.get/post; sqlite3.connect.execute; psycopg2 cursors; file read/write.
  - Record per call-site (file:line) counts and bytes/time; attribute to function via line->FQN mapping.

2.5 Argument-value profiling (novel, implementable)
- Goal: quantify cacheability/candidate repeated computations.
- Implementation:
  - During the second run, wrap hot functions (top-K) with a light decorator that hashes normalized args.
  - Normalization: convert args/kwargs to a JSON-serializable representation:
    - For basic types: str(value).
    - For lists/tuples: tuple of normalized items (truncate long sequences, e.g., first 10 + length).
    - For numpy arrays: shape + dtype + first few elements hashed; do not serialize full array.
    - For dicts: sort keys; use key set + sample of first K items.
  - Maintain a Counter of arg_hash -> count for that function.
  - Compute repetition_rate = (sum(count_i where count_i > 1) / total_calls).
  - Store (function -> repetition_rate, top repeated arg keys).
  - Overhead control: only for top-K hotspots, and only for small number of calls (cap at e.g., 50k).

2.6 Object churn heatmap (implementable, light)
- From tracemalloc snapshots, for each function’s lines inside loops:
  - delta_allocations = allocations_in_loop_body per iteration × estimated iterations (if known).
  - Heuristic: if many small allocations per iteration, flag object churn; suggest pre-allocation or reuse.

2.7 Data collation
- Create a dynamic_metrics table (SQLite):
  - function_id (FQN), inclusive_time_ms, exclusive_time_ms, call_count, avg_time_ms,
  - line_hotspots JSON (top lines, times),
  - memory_alloc_bytes, peak_memory_bytes, allocation_hotspots JSON,
  - io_counts, io_bytes (if enhanced I/O instrumentation used),
  - arg_repetition_rate, top_arg_keys JSON (from 2.5).
- Create dynamic_call_graph edges (caller, callee, time_ms, call_count).

3) Performance fingerprints (how to compute)

Each function gets a PerformanceFingerprint object, stored as JSON in the registry and attached to Vector DB metadata.

Fields and computation
- execution_time: fraction_of_total_runtime = exclusive_time_ms / total_program_time_ms.
- call_count: from pyinstrument or cProfile aggregated.
- memory_delta: from tracemalloc; per-function total allocated bytes during calls (map from lines to function).
- io_operations: total number of I/O calls attributed to function (if instrumented).
- loop_characteristics (static + dynamic):
  - static_nested_depth: computed in 1.3.
  - static_loop_count: number of loops in AST.
  - estimated_iteration_count:
    - If for loops over range(N): use N if N literal; if N name, try to infer constant from defaults or config; otherwise unknown.
    - dynamic proxy: if line_profiler shows repeated execution of body lines >> call_count, estimate iterations ≈ (line_exec_count / call_count) for representative line.
- parallelization_score (heuristic 0-1):
  - Start at 0.
  - +0.3 if function is CPU-bound (cpu_time ~ wall_time, not I/O-bound).
  - +0.2 if loop body has no writes to shared mutable state (static analysis: no assignments to outer-scope variables; no nonlocal/global use; writes only to local accumulators).
  - +0.2 if reductions are used (sum, min, max) or map-like pattern (pure function calls per element).
  - +0.2 if inputs/outputs are numpy arrays or lists of primitives (vectorization possible).
  - -0.3 if heavy Python object creation per iteration (object churn).
  - Cap 0..1.
- cache_efficiency (0-1):
  - From argument-value profiling: repetition_rate; also add +0.2 if function appears pure (static heuristic: no global state, no I/O, returns derived from inputs only).
- Additional optional fields:
  - hot_path_rank: position in top-N hottest functions.
  - exclusive_vs_inclusive_ratio: exclusive_time / inclusive_time.

Rationale
- Fingerprints are a fusion of static heuristics and dynamic evidence. They are implementable with the tools above and give the LLM meaningful, bottleneck-relevant signals.

4) Knowledge base construction

4.1 Vector DB build
- For each FunctionChunk create an embedding payload:
  - text_for_embedding = FQN + signature + short_summary + top_5_called_functions + “loops: depth=x, count=y; CC=z; uses: [list,set,..]”
- Use sentence-transformers (e.g., e5-large-v2) to embed; batch encode for speed.
- Insert into ChromaDB (or FAISS) with metadata:
  - {fqn, module, class, file_path, static_features, fingerprint_summary, ast_hash}
- Create separate collection for:
  - Functions (primary).
  - Classes (signatures only).
  - Modules (for macro refactor context).

4.2 Performance graph (PG)
- Start from static call graph G_static (1.4).
- Overlay dynamic metrics:
  - For each edge caller->callee, set weight = total_time_spent_in_callee_when_called_by_caller (from dynamic_call_graph). If missing, leave weight small to reflect uncertainty.
  - For each node (function), attach node attributes:
    - fingerprint JSON, inclusive/exclusive times, call_count.
- Compute utilities:
  - Hot path extraction: for a given entrypoint (test or main), find the path(s) with max cumulative weights (k-shortest/longest paths).
  - Neighborhood queries: predecessors/successors up to depth d; weighted contribution to a function’s runtime.

4.3 Bottleneck pattern library (you don’t have one → build it)
- Create a YAML/JSON file catalog with entries like:

  - id: AP-ALG-001
    name: Quadratic loop with nested membership checks
    detection:
      static: loop_nesting_depth >= 2 AND “in list” inside inner loop
      dynamic: exclusive_time_high AND line_hotspot_in_loop_body
    fixes:
      - replace list with set for membership
      - precompute dict mapping for lookups
    risks: Ordering semantics, memory overhead
    expected_uplift: 2x-20x depending on N

  - id: AP-CACHE-001
    name: Repeated pure function with same args
    detection:
      dynamic: arg_repetition_rate >= 0.3 AND call_count >= 100
      static: no IO in function, no global state writes
    fixes:
      - functools.lru_cache
      - manual memoization dict
    risks: memory usage; cache invalidation

  - id: AP-VEC-001
    name: Python loops over numeric arrays
    detection:
      static: numpy imported; loops over lists of numbers; operations inside loop simple arithmetic
    fixes:
      - vectorize with numpy
    risks: conversion overhead, dtype issues

  - id: AP-IO-001
    name: Unbatched small I/O
    detection:
      dynamic: high io_operations with small bytes/call
    fixes:
      - batch reads/writes; use buffered I/O
    risks: latency/higher memory

- Start with 8-12 such entries matching your planted issues: algorithmic inefficiency, caching, object churn, vectorization, unbatched I/O, repeated regex compilation, inefficient data structure, unexploited concurrency.
- Tie each pattern to:
  - detection signals (mapping to fingerprint fields or static features),
  - prompt hints (what to tell LLM),
  - example before/after snippets (small, not project-specific) for retrieval in few-shot context.

5) Evidence pack system

Purpose: give minimal, high-signal context to the LLM.

5.1 Evidence pack content (per target function)
- target_function: FQN
- performance_summary:
  - exclusive_time_ms, inclusive_time_ms, fraction_of_total, call_count, avg_time_ms
- bottleneck_signals (aligned with pattern library):
  - loop_characteristics: {depth, count, iteration_estimate}
  - cacheability: {arg_repetition_rate, purity_assessment}
  - memory: {alloc_bytes, churn_flag}
  - io: {io_ops, avg_bytes_per_call}
  - parallelization_score
- code_context:
  - target_code: full body of the function (or a trimmed version if too large).
  - callers: list of top callers (FQN, contribution to target runtime).
  - callees: top callees and their share of inclusive time.
- optimization_hints:
  - Matched patterns from library (IDs, names, summary).
- constraints:
  - existing tests found? (yes/no), dependency availability (numpy installed?), side-effects flags (file writes? network? db?).

5.2 How to assemble
- For each top hotspot by exclusive_time (% >= threshold, e.g., 5%):
  - Select matching patterns by rules from 4.3.
  - Query Performance Graph for callers/callees and contributions.
  - Pull exact code from function registry using file_path and line_range.
- Serialize as JSON for the LLM and keep a human-readable Markdown version for debugging.

6) LLM interaction & tool interface

6.1 Tool interface (model-agnostic)
Expose a fixed set of tools callable by the LLM via JSON:

- list_hotspots(filter): returns ranked list of hot functions with summaries.
- get_function_code(fqn): returns code, signature, fingerprint, static features.
- get_callers(fqn, depth=1): returns callers with their contribution.
- get_callees(fqn, depth=1): returns callees with contribution.
- get_performance_neighborhood(fqn, threshold=0.05): functions contributing > threshold to fqn runtime.
- find_similar_patterns(code_or_features): semantic search over vector DB and pattern library.
- run_tests(): run pytest; return pass/fail, logs.
- run_benchmarks(target=fqn or script): run pyperf harness; return summary (mean, stdev, N, p-value if comparing two versions).
- propose_patch(plan_json): LLM submits a plan for validation (no code applied).
- apply_patch(plan_json): applies plan to a temp branch; returns success/fail with errors.
- rollback(): revert to last accepted commit.

Implementation:
- A Python “tool server” that executes these functions; can be an in-process API when using OpenAI function calling or a simple RPC if needed.
- Ensure consistent JSON schemas for inputs/outputs. Validate with pydantic.

6.2 Prompting strategy
- Triage prompt (general, once per optimization session):
  - Provide: top-K evidence packs (K=3-5), project constraints, pattern library summary (1-paragraph per match).
  - Ask: identify primary bottleneck(s), hypothesize anti-pattern, expected uplift, info needed (which tools to call).
  - Inspired by SBLLM: we encourage stepwise reasoning and “if approach A doesn’t yield uplift, explore B” but do not require explicit genetic-operator wording.

- Focused prompt (per bottleneck type per function):
  - Provide: 1 evidence pack and any extra code requested via tools.
  - Use a bottleneck-specific template (see below) with explicit fields like “Your task: propose a concrete change. If multi-function, output a Transformation Plan JSON (schema below). Include expected speedup and risks.”

- Bottleneck-specific templates
  - Algorithmic, Caching, Vectorization, I/O, Data structure, Parallelization.
  - Each includes detection signals and “what success looks like.”

7) Transformation plan DSL (and how to apply it safely)

7.1 JSON schema (enforced with pydantic)
- Top-level:
  - reasoning: string
  - expected_impact: {speedup_estimate: string or numeric, risk_level: enum, affects_interface: bool}
  - transformations: [TransformationOp]
  - test_requirements: [“existing_tests_pass”, “microbench_pass”]

- TransformationOp types:
  - REPLACE_FUNCTION:
    - target_fqn
    - new_implementation (full function code)
    - preserve_signature: bool
  - ADD_DECORATOR:
    - target_fqn
    - decorator_str (e.g., “@functools.lru_cache(maxsize=128)”)
  - EXTRACT_FUNCTION:
    - from_fqn
    - new_fqn
    - code (new function body)
    - update_call_sites: bool (default true)
  - RENAME_SYMBOL:
    - old_fqn
    - new_fqn
    - update_call_sites: bool
  - MOVE_SYMBOL:
    - from_module
    - to_module
    - symbol_name
  - ADD_IMPORT:
    - target_module
    - module
    - name (optional for from … import …)
  - UPDATE_CALL_SITES:
    - old_fqn
    - new_fqn_or_signature
    - rules (e.g., add new arg with default X)
  - ADD_HELPER_FUNCTION:
    - module
    - code
  - DELETE_SYMBOL:
    - fqn

7.2 Applying plans (AST-safe)
- Use libcst to parse modules and apply edits:
  - For REPLACE_FUNCTION: locate by FQN → replace FunctionDef node; preserve decorators/comments if requested.
  - For ADD_DECORATOR: add decorator node to FunctionDef.
  - For EXTRACT_FUNCTION: insert new FunctionDef into module or class; replace specified code lines (provided as indications) with call to new function; or just update call sites if code param provided.
  - For RENAME/MOVE: update definitions and all import/call sites:
    - Use bowler or rope for project-wide symbol refactors to update references.
- Validation:
  - After applying changes to a temp working copy:
    - Ensure code imports cleanly (python -m pyflakes or ruff check; optional mypy if typed).
    - Ensure unit tests still import.

7.3 Git + function registry updates
- Create an ephemeral branch per candidate (e.g., modelX_runY_bottleneckZ_variantN).
- After successful apply, run tests and perf. If accepted, merge into a main optimization branch.
- Update function registry:
  - Update ast_hash, line ranges if code shifted, module mapping if moved.
  - Record transformation metadata in a “versions” SQLite table:
    - commit_sha, parent_sha, plan_id, target_fqns, success flag, speedup, risks, timestamp.

8) Validation and benchmarking

8.1 Correctness gates
- Run pytest (or provided tests). If tests missing:
  - Ask LLM to generate basic unit tests and property-based tests (Hypothesis) based on function signature and docstrings. You’ll review or auto-run with constraints.
  - Property-based invariants: same return type, idempotency for pure functions, associative/commutative invariants for reducers, preservation of sortedness, etc.

8.2 Performance benchmarking
- Harness: pyperf (preferred) or pytest-benchmark.
  - For a target function:
    - Build micro-benchmark harness (LLM can draft; you finalize). It should reflect realistic inputs (use your test inputs or generators).
  - For end-to-end:
    - Use project’s main script or key entrypoint with fixed inputs.
- Repetitions: pyperf manages calibration and warmup. Collect 20-30 runs per variant if feasible.
- Environment control:
  - CPU pinning via taskset (Linux): “taskset -c 0-1 python run_bench.py”.
  - Disable CPU turbo if possible; or at least log CPU frequency and load.

8.3 Statistical acceptance
- Speedup criterion: >= 10% over baseline AND p < 0.05.
- Test:
  - Use pyperf’s compare module output; or implement a two-sample permutation test on mean times (numpy, scipy).
  - Also consider Cliff’s delta for effect size (optional).
- Regression guard:
  - Measure memory peak; reject if > X% increase (configurable, e.g., 25%).
  - Reject if I/O count multiplies unnecessarily.

9) Version management and the version graph

9.1 Storage
- Use Git as source of truth for code versions (commits/branches).
- Maintain a version graph in SQLite:
  - versions: version_id (commit), parent_version, timestamp, summary, accepted (bool).
  - changes: version_id, operation_type, target_fqn, plan_id, notes.
  - metrics: version_id, speedup_global, speedup_target, memory_delta, tests_passed, p_value.

9.2 Navigation and rollback
- Checkout a given commit to re-run tests/bench.
- Keep artifacts per version (profiles, evidence packs, benchmarks) in artifacts/<project>/versions/<commit>/.

9.3 “Performance frontier”
- Maintain a set of accepted versions that are non-dominated in the (speedup, memory, correctness) space.
- Prefer merging candidates that move the frontier.

10) Optimization loop orchestration

10.1 Controller logic
- For each bottleneck type (sequentially: Algorithmic → Caching → Memory → Vectorization → I/O → Parallelization):
  - Select top-N hotspots by exclusive_time that match the type’s detection signals.
  - For each hotspot:
    - Build evidence pack.
    - Call LLM with focused prompt + tools.
    - Accept a plan if returned; apply; validate; decide accept/reject.
- Iteration control (inspired by SBLLM):
  - If no improvement after M attempts for a hotspot (e.g., M=3), mark as exhausted.
  - If improvement < epsilon for the last K accepted changes (e.g., K=3), stop optimization for this project.

10.2 Time/compute budgeting
- Cap LLM calls per hotspot (e.g., max 10 tool calls + 1-3 code proposals).
- Cap profiling runs per candidate (e.g., 1 microbench + 1 end-to-end).

11) Bottleneck-specific analysis pipelines (concrete)

11.1 Algorithmic complexity pipeline
- Detection signals:
  - static: CC >= threshold (e.g., 10), nested loop depth >= 2, presence of O(n^2) idioms (e.g., list “in” lookups in inner loops).
  - dynamic: exclusive_time high; line_profiler shows inner-loop lines dominating time.
- Evidence focus:
  - Loop structure; data structures used; size of inputs (if inferable).
- Prompts guide the LLM to consider: sorting, sets/dicts, binary search, heap, divide-and-conquer, better algorithmic primitives (bisect, itertools).
- Validation: reduced per-call time; if possible, confirm complexity drop (e.g., removing nested membership checks).

11.2 Caching/memoization pipeline
- Detection signals:
  - dynamic: arg_repetition_rate >= 0.3, call_count high.
  - static: likely pure (no side-effects).
- Evidence focus:
  - Arguments/return types; cache semantics (can we bound cache? invalidation?).
- Prompts include caution about memory growth and TTLs if long-lived.
- Validation: increased cache hit rate (instrument post-change), reduced median time per call.

11.3 Memory/object churn pipeline
- Detection signals:
  - dynamic: high allocation bytes in tight loops; tracemalloc hotspots.
  - static: repeated creation of lists/dicts per iteration.
- Evidence focus:
  - Lines allocating objects; opportunities to pre-allocate or reuse buffers.
- Fixes: move allocations outside loop; reuse lists; array module; bytearray; pre-size lists (rare); object pooling (careful).
- Validation: lower peak memory; lower per-iteration allocations; speedup.

11.4 Vectorization pipeline
- Detection signals:
  - static: loops doing numeric computations; numpy present.
  - dynamic: heavy CPU time in Python loops.
- Fixes: replace Python loops with numpy ops; use numba (optional).
- Validation: significant speedup; possibly increased memory; measure carefully.

11.5 I/O batching pipeline
- Detection signals:
  - dynamic: many small I/O ops; low bytes per call; I/O stalls.
- Fixes: buffered reads/writes; chunked network requests; bulk DB operations.
- Validation: fewer I/O calls; lower wall time.

11.6 Parallelization pipeline
- Detection signals:
  - high parallelization_score; tasks independent; CPU-bound; no shared mutable state.
- Fixes: multiprocessing.Pool for CPU-bound; concurrent.futures; joblib; asyncio for I/O-bound.
- Caution: IPC overhead; GIL; serialization costs.
- Validation: speedup on multi-core; ensure correctness.

12) Evaluation and cross-LLM comparison

12.1 Fairness
- Same tool API, same evidence packs, same budgets.
- Same benchmarks/tests; same seeds; deterministic configs.
- Record: number of tool calls, tokens used, wall time per LLM, plan complexity (operation count).

12.2 Metrics
- Discovery rate: fraction of planted bottlenecks detected (by type).
- Fix success rate: fraction of proposed fixes that pass tests and improve perf.
- Speedup distribution: per-bottleneck and per-project; report mean/median/top-k.
- Edit scope: micro (line/loop), meso (function), macro (cross-module).
- Time-to-fix: elapsed minutes from triage to acceptance.

13) Reproducibility and ops

- Containerize with Docker:
  - Base image: python:3.11-slim; add build-essential for some libs.
- Freeze dependencies: pyproject.toml, lockfile.
- Seed RNG: PYTHONHASHSEED, numpy random seeds.
- Logging and artifacts:
  - Store every prompt, tool call, evidence pack, plan JSON, and profile/benchmark outputs in artifacts/.

14) Optional advanced features (nice-to-have if time permits)

- Pattern mining (novel): after each accepted fix, store before/after code pairs and diffs; later, mine simple patterns to enrich the bottleneck library.
- Lightweight predictive scoring: train a small model (logistic regression) to predict “will this plan reach ≥10% speedup?” from fingerprint features + plan type. Use as a pre-filter.
- Retrieval of external examples: optionally maintain a “snippet gallery” of public optimized idioms (e.g., set membership vs list) for in-context hints.

What’s explicitly inspired by SBLLM
- Iterative refinement as a search process with re-ranking after each iteration.
- The idea of combining ideas across attempts (we translate it to “try different pipelines and plans; if stagnation, pivot bottleneck type”).
- Pattern retrieval guidance (our pattern library plays a similar role, but you curate it rather than retrieving from a pre-trained dataset).

Everything else (performance fingerprints, evidence packs, tool API, plan DSL, statistical acceptance, version graph, bottleneck-specific pipelines) is distinct from SBLLM and makes your thesis novel.

Appendix: Concrete heuristics and thresholds (tunable defaults)
- Top hotspot selection: exclusive_time_frac ≥ 0.05 or top 10 by exclusive_time.
- Algorithmic suspicion: CC ≥ 10 or loop_depth ≥ 2 AND line_hotspot_in_loop.
- Cacheability: arg_repetition_rate ≥ 0.3 and call_count ≥ 100.
- Parallelization_score threshold for consideration: ≥ 0.6.
- Acceptance: speedup ≥ 10% and p < 0.05; memory increase ≤ 25%; tests pass.

Appendix: Data schemas (SQLite)
- functions(fqn TEXT PRIMARY KEY, file_path TEXT, start_line INT, end_line INT, ast_hash TEXT, signature TEXT, docstring TEXT, class_name TEXT, module_name TEXT, decorators JSON, imports JSON, callers JSON, callees JSON, static_features JSON, fingerprint JSON)
- dynamic_metrics(fqn TEXT, run_id TEXT, incl_ms REAL, excl_ms REAL, call_count INT, line_hotspots JSON, mem_alloc_bytes REAL, peak_mem_bytes REAL, io_counts INT, io_bytes REAL, arg_repetition REAL, top_args JSON)
- versions(version_id TEXT PRIMARY KEY, parent_version TEXT, timestamp TEXT, accepted INT, summary TEXT)
- changes(version_id TEXT, op_type TEXT, target_fqn TEXT, plan_id TEXT, notes TEXT)
- metrics(version_id TEXT, speedup_global REAL, speedup_target REAL, memory_delta REAL, tests_passed INT, p_value REAL)

Appendix: Evidence pack JSON (example skeleton)
{
  "target_function": "pkg.module.Class.fn",
  "performance_summary": {
    "exclusive_time_ms": 415.2,
    "inclusive_time_ms": 530.8,
    "fraction_of_total": 0.42,
    "call_count": 150,
    "avg_time_ms": 3.54
  },
  "bottleneck_signals": {
    "loop_characteristics": {"depth": 2, "count": 3, "iteration_estimate": "~n* m"},
    "cacheability": {"arg_repetition_rate": 0.41, "purity": "likely"},
    "memory": {"alloc_bytes": 12_000_000, "churn": "high"},
    "io": {"ops": 0, "avg_bytes": 0},
    "parallelization_score": 0.7
  },
  "code_context": {
    "target_code": "...",
    "callers": [{"fqn": "...", "contrib_frac": 0.33}],
    "callees": [{"fqn": "...", "contrib_frac": 0.24}]
  },
  "optimization_hints": [
    {"pattern_id": "AP-CACHE-001", "name": "Repeated pure function", "expected_uplift": "10-50%"}
  ],
  "constraints": {"has_tests": true, "numpy_available": true, "side_effects": ["none"]}
}

With this, you can start implementing PEARL end-to-end. If you want, I can also draft the exact LLM prompt templates (triage + each bottleneck-specific) and the pydantic schemas for the plan DSL and evidence packs so you can paste them into your codebase.