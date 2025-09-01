# PEARL: Performance Evidence-Augmented Refactoring with LLMs

## Complete Implementation Architecture with Detailed Instructions

### System Architecture Overview (Expanded)

```
┌─────────────────────────────────────────────────────────────┐
│                     INITIALIZATION PHASE                    │
├─────────────────────────────────────────────────────────────┤
│ 1. Code Analysis Pipeline                                   │
│    ├── 1.1 Project Discovery & Setup                        │
│    ├── 1.2 AST Parsing → Function/Class Chunks              │
│    ├── 1.3 Static Analysis → Call Graph, Complexity Metrics │
│    └── 1.4 Dynamic Profiling → Performance Fingerprints     │
│                                                             │
│ 2. Knowledge Base Construction                              │
│    ├── 2.1 Vector DB Creation (code chunks + fingerprints)  │
│    ├── 2.2 Performance Graph (PG) Building                  │
│    └── 2.3 Bottleneck Pattern Library Generation            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    OPTIMIZATION LOOP                        │
├─────────────────────────────────────────────────────────────┤
│ For each bottleneck type (sequential):                      │
│                                                             │
│ 3. Evidence Assembly                                        │
│    ├── 3.1 Bottleneck Detection & Prioritization            │
│    ├── 3.2 Context Collection                               │
│    └── 3.3 Evidence Pack Generation                         │
│                                                             │
│ 4. LLM Analysis (with Tool Access)                          │
│    ├── 4.1 Initial Prompt Construction                      │
│    ├── 4.2 Tool-based Interactive Exploration               │
│    └── 4.3 Transformation Plan Generation                   │
│                                                             │
│ 5. Transformation & Validation                              │
│    ├── 5.1 AST-based Code Transformation                    │
│    ├── 5.2 Syntax & Type Validation                         │
│    ├── 5.3 Test Suite Execution                             │
│    └── 5.4 Performance Benchmarking                         │
│                                                             │
│ 6. Version Management & Decision                            │
│    ├── 6.1 Version Graph Update                             │
│    ├── 6.2 Statistical Significance Testing                 │
│    └── 6.3 Commit or Rollback Decision                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      EVALUATION PHASE                       │
├─────────────────────────────────────────────────────────────┤
│ 7. Metrics Collection & Analysis                            │
│    ├── 7.1 Performance Uplift Calculation                   │
│    ├── 7.2 LLM Comparison Metrics                           │
│    └── 7.3 Bottleneck-specific Success Analysis             │
└─────────────────────────────────────────────────────────────┘
```

## Detailed Implementation Instructions

### Phase 1: Code Analysis Pipeline

#### 1.1 Project Discovery & Setup

**Implementation Steps:**

1. **Project Structure Analysis**
    - Use `pathlib` to traverse the project directory
    - Identify Python files using glob patterns: `**/*.py`
    - Create a project manifest storing:
        - All Python file paths
        - Main entry points (files with `if __name__ == "__main__"`)
        - Package structure (directories with `__init__.py`)
        - Requirements (parse `requirements.txt` or `pyproject.toml`)

2. **Dependency Resolution**
    - Use `pipreqs` or `pip-tools` to identify external dependencies
    - Create isolated virtual environment for testing
    - Install dependencies and verify imports work

3. **Test Discovery**
    - Locate test files (pattern: `test_*.py` or `*_test.py`)
    - Identify test framework (pytest, unittest, nose)
    - Create test execution commands for later validation

**Libraries:** `pathlib`, `glob`, `pipreqs`, `virtualenv`, `ast`

#### 1.2 AST Parsing → Function/Class Chunks

**Implementation:**

1. **Parse Python Files into AST**
   ```python
   # Use Python's ast module
   import ast
   import astunparse  # for converting AST back to code
   
   # For each Python file:
   # 1. Read file content
   # 2. Parse into AST: tree = ast.parse(content, filename)
   # 3. Walk the tree to extract nodes
   ```

2. **Extract Code Chunks**
    - **Function Extraction:**
        - Visit all `ast.FunctionDef` and `ast.AsyncFunctionDef` nodes
        - For each function, extract:
            - Full function code (use `astunparse.unparse()`)
            - Function name, parameters, return annotation
            - Decorators list
            - Docstring (first `ast.Constant` in body if string)
            - Line numbers (node.lineno to node.end_lineno)

    - **Class Extraction:**
        - Visit all `ast.ClassDef` nodes
        - Extract class definition with all methods
        - Store inheritance information (base classes)
        - Track class-level attributes

3. **Generate Unique IDs**
    - Format: `module_path.ClassName.method_name`
    - Example: `src.data_processor.DataHandler.process_batch`
    - Store mapping: ID → (file_path, line_range, ast_node)

**Data Structure:**

```python
class CodeChunk:
    id: str  # Unique identifier
    chunk_type: str  # "function", "method", "class", "module"
    code: str  # Original source code
    ast_node: ast.Node  # Preserved AST node
    file_path: Path
    line_range: Tuple[int, int]
    parent_class: Optional[str]  # For methods
    imports: List[str]  # Extracted from module level
    decorators: List[str]
    docstring: Optional[str]
    signature: str  # Function/method signature
```

**Libraries:** `ast`, `astunparse`, `astor` (alternative AST manipulation)

#### 1.3 Static Analysis → Call Graph, Complexity Metrics

**Implementation:**

1. **Call Graph Construction**
    - **Using `pyan3`:**
      ```bash
      pip install pyan3
      # Generate call graph: pyan *.py --dot > callgraph.dot
      ```
    - **Custom AST-based approach:**
        - Visit all `ast.Call` nodes in each function
        - Resolve call targets (consider imports, class methods)
        - Build adjacency list: `caller_id → [callee_ids]`
        - Handle dynamic calls conservatively (mark as "unknown")

2. **Complexity Metrics Calculation**

   **Cyclomatic Complexity:**
    - Use `radon` library: `pip install radon`
    - For each function: `cc = radon.complexity.cc_visit(code)`
    - Complexity = number of decision points + 1
    - Decision points: if, elif, for, while, except, with, and, or

   **Cognitive Complexity:**
    - Use `cognitive-complexity` library
    - Accounts for nesting depth and complexity of conditions
    - More accurate for human comprehension difficulty

   **Lines of Code Metrics:**
    - LOC: Total lines
    - SLOC: Source lines (excluding comments/blanks)
    - Use `radon.raw.analyze(code)`

3. **Data Flow Analysis**
    - **Variable Usage Tracking:**
        - Visit `ast.Name` nodes with context (Load/Store/Del)
        - Track which functions read/write shared variables
        - Identify global variable usage

    - **Parameter Flow:**
        - Track how parameters are passed between functions
        - Identify functions that transform and pass data

**Output Structure:**

```python
class StaticAnalysisResult:
    call_graph: Dict[str, List[str]]  # caller → callees
    reverse_call_graph: Dict[str, List[str]]  # callee → callers
    complexity_metrics: Dict[str, Dict]  # function_id → metrics
    # metrics = {
    #     'cyclomatic': int,
    #     'cognitive': int,
    #     'loc': int,
    #     'sloc': int,
    #     'parameter_count': int,
    #     'return_points': int
    # }
    data_dependencies: Dict[str, Set[str]]  # function → accessed variables
    import_graph: Dict[str, Set[str]]  # module → imported modules
```

**Libraries:** `radon`, `pyan3`, `cognitive-complexity`, `networkx` (for graph operations)

#### 1.4 Dynamic Profiling → Performance Fingerprints

**Implementation:**

1. **Setup Profiling Infrastructure**

   **CPU Profiling:**
    - Use `cProfile` for function-level profiling
    - Use `line_profiler` for line-level profiling
    - Use `py-spy` for sampling profiler (lower overhead)

   ```python
   # Setup approach:
   # 1. Create test scenario that exercises the code
   # 2. Run with profiler:
   import cProfile
   import pstats
   
   profiler = cProfile.Profile()
   profiler.enable()
   # Run test workload
   profiler.disable()
   stats = pstats.Stats(profiler)
   ```

   **Memory Profiling:**
    - Use `memory_profiler` for line-by-line memory
    - Use `tracemalloc` for memory allocation tracking

   ```python
   import tracemalloc
   tracemalloc.start()
   # Run code
   snapshot = tracemalloc.take_snapshot()
   ```

2. **Calculate Performance Fingerprint Components**

   **execution_time (percentage of total runtime):**
   ```python
   # From cProfile stats:
   total_time = sum(stats.stats[func][2] for func in stats.stats)
   function_time = stats.stats[function_key][2]  # cumulative time
   execution_time_percent = (function_time / total_time) * 100
   ```

   **call_count:**
   ```python
   # Direct from cProfile stats
   call_count = stats.stats[function_key][0]
   ```

   **memory_delta:**
   ```python
   # Using tracemalloc snapshots
   # Take snapshot before and after function execution
   # Calculate difference in memory usage
   memory_before = snapshot1.statistics('lineno')
   memory_after = snapshot2.statistics('lineno')
   memory_delta = sum(stat.size for stat in memory_after) - sum(stat.size for stat in memory_before)
   ```

   **io_operations count:**
   ```python
   # Monkey-patch I/O functions to count calls
   import io
   import builtins
   
   io_counter = 0
   original_open = builtins.open
   
   def counting_open(*args, **kwargs):
       global io_counter
       io_counter += 1
       return original_open(*args, **kwargs)
   
   builtins.open = counting_open
   # Run code
   # Restore and get count
   ```

   **loop_characteristics:**
   ```python
   # Static analysis of AST + dynamic execution count
   def analyze_loops(ast_node):
       loop_info = {
           'nested_depth': 0,
           'iteration_estimate': 0,
           'loop_types': []  # 'for', 'while', 'comprehension'
       }
       
       # Visit AST to find loops
       for node in ast.walk(ast_node):
           if isinstance(node, (ast.For, ast.While)):
               # Calculate nesting by checking parent nodes
               # Use profiler data to estimate iterations
       
       return loop_info
   ```

   **parallelization_score (0-1 scale):**
   ```python
   def calculate_parallelization_score(function_ast, data_dependencies):
       score = 1.0
       
       # Reduce score for:
       # - Global variable writes (not thread-safe)
       if has_global_writes(function_ast):
           score *= 0.5
       
       # - Shared mutable state
       if has_shared_state(data_dependencies):
           score *= 0.7
           
       # - I/O operations (GIL-bound)
       if has_io_operations(function_ast):
           score *= 0.6
           
       # - Dependencies between loop iterations
       if has_loop_dependencies(function_ast):
           score *= 0.4
           
       return score
   ```

   **cache_efficiency (repeated calls with same arguments):**
   ```python
   # Instrument function to track arguments
   from functools import wraps
   import hashlib
   
   call_history = {}
   
   def track_calls(func):
       @wraps(func)
       def wrapper(*args, **kwargs):
           # Hash arguments for comparison
           arg_hash = hashlib.md5(str((args, kwargs)).encode()).hexdigest()
           
           if func.__name__ not in call_history:
               call_history[func.__name__] = []
           
           call_history[func.__name__].append(arg_hash)
           return func(*args, **kwargs)
       return wrapper
   
   # After execution:
   def calculate_cache_efficiency(func_name):
       if func_name not in call_history:
           return 0.0
       
       calls = call_history[func_name]
       unique_calls = len(set(calls))
       total_calls = len(calls)
       
       if total_calls == 0:
           return 0.0
           
       repetition_rate = 1 - (unique_calls / total_calls)
       return repetition_rate
   ```

**Libraries:** `cProfile`, `line_profiler`, `memory_profiler`, `tracemalloc`, `py-spy`

### Phase 2: Knowledge Base Construction

#### 2.1 Vector DB Creation

**Implementation:**

1. **Code Embedding Generation**

   **Approach 1: Using CodeBERT**
   ```python
   from transformers import AutoTokenizer, AutoModel
   import torch
   
   # Load CodeBERT
   tokenizer = AutoTokenizer.from_pretrained("microsoft/codebert-base")
   model = AutoModel.from_pretrained("microsoft/codebert-base")
   
   def embed_code(code_string):
       inputs = tokenizer(code_string, return_tensors="pt", 
                         max_length=512, truncation=True)
       with torch.no_grad():
           outputs = model(**inputs)
       # Use pooled output or mean of last hidden states
       embedding = outputs.last_hidden_state.mean(dim=1)
       return embedding.numpy()
   ```

   **Approach 2: Using OpenAI Embeddings**
   ```python
   import openai
   
   def embed_code(code_string):
       response = openai.Embedding.create(
           model="text-embedding-ada-002",
           input=code_string
       )
       return response['data'][0]['embedding']
   ```

2. **Vector Database Setup**

   **Using ChromaDB:**
   ```python
   import chromadb
   from chromadb.config import Settings
   
   # Initialize ChromaDB
   client = chromadb.Client(Settings(
       chroma_db_impl="duckdb+parquet",
       persist_directory="./chroma_db"
   ))
   
   # Create collection
   collection = client.create_collection(
       name="code_chunks",
       metadata={"hnsw:space": "cosine"}
   )
   
   # Add documents
   for chunk in code_chunks:
       # Prepare metadata
       metadata = {
           "chunk_id": chunk.id,
           "file_path": str(chunk.file_path),
           "chunk_type": chunk.chunk_type,
           "complexity": chunk.complexity_metrics['cyclomatic'],
           "execution_time": chunk.performance_fingerprint.execution_time,
           "call_count": chunk.performance_fingerprint.call_count
       }
       
       # Create searchable document
       document = f"{chunk.docstring}\n{chunk.signature}\n{chunk.code}"
       
       # Add to collection
       collection.add(
           documents=[document],
           metadatas=[metadata],
           ids=[chunk.id],
           embeddings=[embed_code(chunk.code)]
       )
   ```

**Index Organization:**

- Primary index: Code embeddings for semantic search
- Secondary indices on metadata:
    - Performance metrics (execution_time, memory_delta)
    - Complexity metrics
    - File path and module structure
    - Chunk type (function, class, method)

**Libraries:** `chromadb`, `transformers`, `sentence-transformers`, `faiss` (alternative)

#### 2.2 Performance Graph Building

**Implementation:**

1. **Graph Structure Creation**

   ```python
   import networkx as nx
   import json
   
   # Create directed graph
   perf_graph = nx.DiGraph()
   
   # Add nodes (functions/classes)
   for chunk in code_chunks:
       node_attrs = {
           'type': chunk.chunk_type,
           'code': chunk.code,
           'fingerprint': chunk.performance_fingerprint.__dict__,
           'complexity': chunk.complexity_metrics,
           'file_path': str(chunk.file_path),
           'line_range': chunk.line_range
       }
       perf_graph.add_node(chunk.id, **node_attrs)
   
   # Add edges (call relationships)
   for caller_id, callee_ids in call_graph.items():
       for callee_id in callee_ids:
           if caller_id in perf_graph and callee_id in perf_graph:
               # Calculate edge weight based on performance impact
               caller_time = perf_graph.nodes[caller_id]['fingerprint']['execution_time']
               callee_time = perf_graph.nodes[callee_id]['fingerprint']['execution_time']
               
               # Weight represents portion of caller's time spent in callee
               weight = callee_time / caller_time if caller_time > 0 else 0
               
               perf_graph.add_edge(caller_id, callee_id, 
                                  weight=weight,
                                  call_count=call_counts.get((caller_id, callee_id), 1))
   ```

2. **Performance Hotspot Detection**

   ```python
   def identify_hotspots(perf_graph, threshold=5.0):
       """Identify performance hotspots (functions > threshold% runtime)"""
       hotspots = []
       
       for node_id, attrs in perf_graph.nodes(data=True):
           exec_time = attrs['fingerprint']['execution_time']
           if exec_time > threshold:
               hotspots.append({
                   'id': node_id,
                   'execution_time': exec_time,
                   'complexity': attrs['complexity']['cyclomatic'],
                   'call_count': attrs['fingerprint']['call_count']
               })
       
       # Sort by execution time
       hotspots.sort(key=lambda x: x['execution_time'], reverse=True)
       return hotspots
   ```

3. **Critical Path Analysis**

   ```python
   def find_critical_paths(perf_graph, start_node='main'):
       """Find execution paths with highest cumulative time"""
       critical_paths = []
       
       # Use DFS to find all paths from start
       for target in perf_graph.nodes():
           if target != start_node:
               try:
                   # Find shortest path (considering negative weights for high cost)
                   path = nx.shortest_path(perf_graph, start_node, target, 
                                          weight=lambda u,v,d: -d['weight'])
                   
                   # Calculate cumulative time
                   path_time = sum(perf_graph.nodes[n]['fingerprint']['execution_time'] 
                                 for n in path)
                   
                   critical_paths.append({
                       'path': path,
                       'total_time': path_time
                   })
               except nx.NetworkXNoPath:
                   continue
       
       # Return top critical paths
       critical_paths.sort(key=lambda x: x['total_time'], reverse=True)
       return critical_paths[:10]
   ```

**Graph Persistence:**

```python
# Save graph
nx.write_gpickle(perf_graph, "performance_graph.gpickle")

# Or as JSON for portability
from networkx.readwrite import json_graph

graph_data = json_graph.node_link_data(perf_graph)
with open('performance_graph.json', 'w') as f:
    json.dump(graph_data, f)
```

**Libraries:** `networkx`, `pygraphviz` (for visualization), `plotly` (interactive viz)

#### 2.3 Bottleneck Pattern Library Generation

Since you don't have a pre-existing library, we'll create one:

**Implementation:**

1. **Define Bottleneck Pattern Templates**

   ```python
   BOTTLENECK_PATTERNS = {
       "inefficient_algorithm": {
           "id": "ALG001",
           "name": "Quadratic Algorithm",
           "description": "Nested loops over same collection",
           "detection_rules": {
               "ast_pattern": "nested_for_same_iterable",
               "complexity_threshold": 10,  # Cyclomatic complexity
               "performance_signature": {
                   "execution_time": ">10%",
                   "growth_pattern": "quadratic"  # From multiple test runs
               }
           },
           "example_code": """
   # Bad
   for i in items:
       for j in items:
           if i.id == j.parent_id:
               # process
   
   # Good
   parent_map = {j.parent_id: j for j in items}
   for i in items:
       if i.id in parent_map:
           # process
           """,
           "suggested_fix": "Use dictionary/set for O(1) lookups",
           "expected_improvement": "O(n²) → O(n)"
       },
       
       "missing_cache": {
           "id": "CACHE001",
           "name": "Repeated Expensive Computation",
           "description": "Same expensive function called with same arguments",
           "detection_rules": {
               "cache_efficiency": ">0.3",  # 30% repeated calls
               "execution_time": ">1%",
               "is_pure_function": True
           },
           "suggested_fix": "Add @lru_cache or memoization",
           "expected_improvement": "Proportional to repetition rate"
       },
       
       "object_recreation": {
           "id": "MEM001",
           "name": "Object Recreation in Loop",
           "description": "Creating objects inside loops that could be reused",
           "detection_rules": {
               "ast_pattern": "object_creation_in_loop",
               "memory_delta": ">10MB",
               "loop_iterations": ">100"
           },
           "suggested_fix": "Pre-allocate or reuse objects",
           "expected_improvement": "Reduce allocation overhead"
       },
       
       "synchronous_io": {
           "id": "IO001",
           "name": "Synchronous I/O in Loop",
           "description": "Multiple blocking I/O operations that could be batched",
           "detection_rules": {
               "io_operations": ">10",
               "in_loop": True,
               "parallelization_score": "<0.3"
           },
           "suggested_fix": "Batch I/O operations or use async",
           "expected_improvement": "Linear to significant based on I/O latency"
       },
       
       "unused_parallelism": {
           "id": "PAR001",
           "name": "Parallelizable Sequential Processing",
           "description": "Independent iterations processed sequentially",
           "detection_rules": {
               "parallelization_score": ">0.7",
               "execution_time": ">5%",
               "loop_iterations": ">100",
               "no_shared_state": True
           },
           "suggested_fix": "Use multiprocessing.Pool or concurrent.futures",
           "expected_improvement": "Up to N× on N cores"
       }
   }
   ```

2. **Pattern Detection Implementation**

   ```python
   class BottleneckDetector:
       def __init__(self, patterns, code_chunks, perf_graph):
           self.patterns = patterns
           self.code_chunks = code_chunks
           self.perf_graph = perf_graph
       
       def detect_patterns(self, chunk_id):
           """Detect which bottleneck patterns match a code chunk"""
           detected = []
           chunk = self.code_chunks[chunk_id]
           
           for pattern_id, pattern in self.patterns.items():
               if self._matches_pattern(chunk, pattern):
                   detected.append({
                       'pattern_id': pattern_id,
                       'confidence': self._calculate_confidence(chunk, pattern),
                       'expected_improvement': pattern['expected_improvement']
                   })
           
           return detected
       
       def _matches_pattern(self, chunk, pattern):
           """Check if chunk matches pattern detection rules"""
           rules = pattern['detection_rules']
           
           # Check performance thresholds
           if 'execution_time' in rules:
               threshold = float(rules['execution_time'].strip('>%'))
               if chunk.performance_fingerprint.execution_time < threshold:
                   return False
           
           # Check AST patterns
           if 'ast_pattern' in rules:
               if not self._check_ast_pattern(chunk.ast_node, rules['ast_pattern']):
                   return False
           
           # Check metrics
           for metric, threshold in rules.items():
               if hasattr(chunk.performance_fingerprint, metric):
                   value = getattr(chunk.performance_fingerprint, metric)
                   if not self._check_threshold(value, threshold):
                       return False
           
           return True
       
       def _check_ast_pattern(self, ast_node, pattern_name):
           """Check for specific AST patterns"""
           if pattern_name == "nested_for_same_iterable":
               # Look for nested for loops over same variable
               return self._has_nested_loops(ast_node)
           elif pattern_name == "object_creation_in_loop":
               # Look for object instantiation inside loops
               return self._has_object_creation_in_loop(ast_node)
           # Add more patterns...
           return False
   ```

3. **AST Pattern Checking Functions**

   ```python
   def _has_nested_loops(self, ast_node):
       """Check for nested loops over same iterable"""
       for node in ast.walk(ast_node):
           if isinstance(node, ast.For):
               # Check if inner loop exists
               for inner in ast.walk(node):
                   if inner != node and isinstance(inner, ast.For):
                       # Check if they iterate over related variables
                       outer_iter = node.iter
                       inner_iter = inner.iter
                       
                       # Simple check: same variable name
                       if isinstance(outer_iter, ast.Name) and isinstance(inner_iter, ast.Name):
                           if outer_iter.id == inner_iter.id:
                               return True
       return False
   
   def _has_object_creation_in_loop(self, ast_node):
       """Check for object creation inside loops"""
       for node in ast.walk(ast_node):
           if isinstance(node, (ast.For, ast.While)):
               for inner in ast.walk(node):
                   # Look for class instantiation
                   if isinstance(inner, ast.Call):
                       if isinstance(inner.func, ast.Name):
                           # Check if it's a class (capitalized)
                           if inner.func.id[0].isupper():
                               return True
                       # Check for list(), dict(), set() calls
                       if isinstance(inner.func, ast.Name):
                           if inner.func.id in ['list', 'dict', 'set', 'tuple']:
                               return True
       return False
   ```

**Libraries:** Pattern library is built from scratch using AST analysis

### Phase 3: Evidence Assembly

#### 3.1 Bottleneck Detection & Prioritization

**Implementation:**

```python
class BottleneckPrioritizer:
    def __init__(self, perf_graph, detector, code_chunks):
        self.perf_graph = perf_graph
        self.detector = detector
        self.code_chunks = code_chunks

    def prioritize_bottlenecks(self):
        """Identify and rank bottlenecks by impact"""
        bottlenecks = []

        # Get hotspots from performance graph
        hotspots = identify_hotspots(self.perf_graph, threshold=1.0)

        for hotspot in hotspots:
            chunk_id = hotspot['id']

            # Detect matching patterns
            patterns = self.detector.detect_patterns(chunk_id)

            if patterns:
                # Calculate priority score
                priority_score = self._calculate_priority(hotspot, patterns)

                bottlenecks.append({
                    'chunk_id': chunk_id,
                    'execution_time': hotspot['execution_time'],
                    'patterns': patterns,
                    'priority_score': priority_score,
                    'estimated_improvement': self._estimate_improvement(patterns)
                })

        # Sort by priority
        bottlenecks.sort(key=lambda x: x['priority_score'], reverse=True)
        return bottlenecks

    def _calculate_priority(self, hotspot, patterns):
        """Calculate priority based on impact and ease of fix"""
        # Base score from execution time
        time_score = hotspot['execution_time']

        # Multiply by confidence of pattern detection
        confidence_multiplier = max(p['confidence'] for p in patterns)

        # Adjust for complexity (easier fixes get higher priority)
        complexity_penalty = min(1.0, 10.0 / (hotspot['complexity'] + 1))

        return time_score * confidence_multiplier * complexity_penalty

    def _estimate_improvement(self, patterns):
        """Estimate potential improvement from fixing patterns"""
        # Combine improvements (diminishing returns)
        total_improvement = 0
        for pattern in patterns:
            improvement = pattern.get('expected_improvement', 'unknown')
            # Parse improvement (e.g., "2x" -> 2.0, "O(n²) → O(n)" -> estimate)
            if isinstance(improvement, str):
                if 'x' in improvement:
                    factor = float(improvement.replace('x', ''))
                    total_improvement = max(total_improvement, factor)
                elif 'O(n²) → O(n)' in improvement:
                    total_improvement = max(total_improvement, 10.0)  # Estimate
                # Add more parsing rules

        return total_improvement
```

#### 3.2 Context Collection

**Implementation:**

```python
class ContextCollector:
    def __init__(self, code_chunks, call_graph, perf_graph, vector_db):
        self.code_chunks = code_chunks
        self.call_graph = call_graph
        self.perf_graph = perf_graph
        self.vector_db = vector_db

    def collect_context(self, target_chunk_id, bottleneck_type):
        """Collect relevant context for a bottleneck"""
        context = {
            'target': self._get_target_context(target_chunk_id),
            'callers': self._get_callers_context(target_chunk_id),
            'callees': self._get_callees_context(target_chunk_id),
            'performance_neighborhood': self._get_performance_neighborhood(target_chunk_id),
            'similar_code': self._get_similar_code(target_chunk_id),
            'bottleneck_specific': self._get_bottleneck_specific_context(
                target_chunk_id, bottleneck_type
            )
        }
        return context

    def _get_target_context(self, chunk_id):
        """Get full context for target function"""
        chunk = self.code_chunks[chunk_id]
        return {
            'code': chunk.code,
            'signature': chunk.signature,
            'docstring': chunk.docstring,
            'complexity': chunk.complexity_metrics,
            'fingerprint': chunk.performance_fingerprint.__dict__,
            'ast_structure': self._simplify_ast(chunk.ast_node)
        }

    def _get_callers_context(self, chunk_id, max_callers=3):
        """Get context for functions that call target"""
        callers = self.call_graph.get_callers(chunk_id)[:max_callers]

        caller_contexts = []
        for caller_id in callers:
            caller_chunk = self.code_chunks[caller_id]

            # Extract just the part that calls our target
            call_context = self._extract_call_context(caller_chunk, chunk_id)

            caller_contexts.append({
                'id': caller_id,
                'signature': caller_chunk.signature,
                'call_context': call_context,
                'call_count': self._get_call_count(caller_id, chunk_id)
            })

        return caller_contexts

    def _get_performance_neighborhood(self, chunk_id):
        """Get functions that contribute significantly to target's runtime"""
        neighbors = []

        # Get functions called by target
        if chunk_id in self.call_graph.adjacency:
            for callee_id in self.call_graph.adjacency[chunk_id]:
                callee_time = self.perf_graph.nodes[callee_id]['fingerprint']['execution_time']

                # Include if contributes >5% of target's time
                target_time = self.perf_graph.nodes[chunk_id]['fingerprint']['execution_time']
                if callee_time > target_time * 0.05:
                    neighbors.append({
                        'id': callee_id,
                        'contribution': callee_time / target_time,
                        'summary': self._get_function_summary(callee_id)
                    })

        return neighbors

    def _get_bottleneck_specific_context(self, chunk_id, bottleneck_type):
        """Get context specific to bottleneck type"""
        chunk = self.code_chunks[chunk_id]

        if bottleneck_type == "algorithmic_complexity":
            return {
                'loop_analysis': self._analyze_loops_detailed(chunk.ast_node),
                'data_structures': self._analyze_data_structures(chunk.ast_node),
                'algorithm_hints': self._suggest_algorithms(chunk.ast_node)
            }

        elif bottleneck_type == "caching_opportunities":
            return {
                'argument_patterns': self._analyze_argument_patterns(chunk_id),
                'purity_analysis': self._check_function_purity(chunk.ast_node),
                'memoization_candidates': self._find_memoization_candidates(chunk.ast_node)
            }

        elif bottleneck_type == "unused_parallelism":
            return {
                'dependency_analysis': self._analyze_dependencies(chunk.ast_node),
                'gil_impact': self._estimate_gil_impact(chunk.ast_node),
                'parallelization_strategy': self._suggest_parallelization(chunk.ast_node)
            }

        # Add more bottleneck types...
        return {}
```

#### 3.3 Evidence Pack Generation

**Implementation:**

```python
class EvidencePackGenerator:
    def __init__(self, context_collector, pattern_library):
        self.context_collector = context_collector
        self.pattern_library = pattern_library

    def generate_evidence_pack(self, bottleneck):
        """Generate complete evidence pack for LLM"""
        chunk_id = bottleneck['chunk_id']
        patterns = bottleneck['patterns']

        # Determine primary bottleneck type
        primary_pattern = patterns[0]['pattern_id']
        bottleneck_type = self._get_bottleneck_type(primary_pattern)

        # Collect context
        context = self.context_collector.collect_context(chunk_id, bottleneck_type)

        # Generate bottleneck-specific signals
        signals = self._generate_signals(context, bottleneck_type)

        # Build evidence pack
        evidence_pack = {
            'target_function': chunk_id,
            'performance_summary': {
                'execution_time_percent': context['target']['fingerprint']['execution_time'],
                'memory_usage_mb': context['target']['fingerprint']['memory_delta'] / 1024 / 1024,
                'call_count': context['target']['fingerprint']['call_count'],
                'complexity': context['target']['complexity']
            },
            'bottleneck_signals': signals,
            'code_context': {
                'target_code': context['target']['code'],
                'callers': context['callers'],
                'callees': context['callees'],
                'performance_neighborhood': context['performance_neighborhood']
            },
            'optimization_hints': self._get_optimization_hints(patterns),
            'constraints': self._identify_constraints(context),
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'bottleneck_type': bottleneck_type,
                'confidence': max(p['confidence'] for p in patterns)
            }
        }

        return evidence_pack

    def _generate_signals(self, context, bottleneck_type):
        """Generate bottleneck-specific signals from context"""
        signals = {}

        if bottleneck_type == "algorithmic_complexity":
            signals = {
                'nested_loops': len(context['bottleneck_specific']['loop_analysis']['nested_loops']),
                'estimated_complexity': context['bottleneck_specific']['loop_analysis']['complexity'],
                'data_structure_operations': context['bottleneck_specific']['data_structures'],
                'suggested_algorithms': context['bottleneck_specific']['algorithm_hints']
            }

        elif bottleneck_type == "caching_opportunities":
            signals = {
                'argument_repetition_rate': context['bottleneck_specific']['argument_patterns']['repetition_rate'],
                'is_pure': context['bottleneck_specific']['purity_analysis']['is_pure'],
                'side_effects': context['bottleneck_specific']['purity_analysis']['side_effects'],
                'cache_size_estimate': context['bottleneck_specific']['argument_patterns']['unique_args_count']
            }

        # Add more bottleneck types...

        return signals

    def _identify_constraints(self, context):
        """Identify constraints for optimization"""
        constraints = {
            'has_tests': self._check_test_coverage(context['target']['code']),
            'has_type_hints': self._check_type_hints(context['target']['signature']),
            'external_dependencies': self._find_external_deps(context['target']['code']),
            'side_effects': self._identify_side_effects(context['target']['ast_structure']),
            'thread_safety_required': self._check_thread_safety_requirement(context),
            'memory_constraints': self._estimate_memory_constraints()
        }
        return constraints
```

### Phase 4: LLM Analysis with Tool Access

#### 4.1 Initial Prompt Construction

**Implementation:**

```python
class PromptConstructor:
    def __init__(self, prompt_templates):
        self.templates = prompt_templates

    def construct_initial_prompt(self, evidence_pack, bottleneck_type):
        """Build initial prompt for LLM"""

        # Select template based on bottleneck type
        template = self.templates[bottleneck_type]

        # Format evidence pack into readable structure
        formatted_evidence = self._format_evidence(evidence_pack)

        # Build prompt
        prompt = f"""
# Performance Optimization Task

## Context
You are analyzing a Python function that has been identified as a performance bottleneck.
Your goal is to propose an optimization that addresses the {bottleneck_type} issue.

## Performance Profile
{formatted_evidence['performance_summary']}

## Bottleneck Indicators
{formatted_evidence['signals']}

## Target Function
```python
{evidence_pack['code_context']['target_code']}
```

## Calling Context

{formatted_evidence['calling_context']}

## Constraints

{formatted_evidence['constraints']}

## Your Task

1. Analyze the bottleneck based on the provided evidence
2. Use the available tools to explore related code if needed
3. Propose an optimization that:
    - Addresses the identified bottleneck type
    - Maintains functional correctness
    - Respects the identified constraints
4. Provide your solution as a structured transformation plan

## Available Tools

You can call these functions to get more information:

- get_function_code(function_id): Get code for a specific function
- get_callers(function_id): Get functions that call the target
- get_callees(function_id): Get functions called by the target
- get_performance_neighborhood(function_id): Get performance-related functions
- find_similar_patterns(code_pattern): Find similar code in the codebase
- check_dependencies(function_id): Check external dependencies

{template['specific_instructions']}
"""
return prompt

    def _format_evidence(self, evidence_pack):
        """Format evidence pack for readability"""
        formatted = {
            'performance_summary': self._format_performance_summary(
                evidence_pack['performance_summary']
            ),
            'signals': self._format_signals(
                evidence_pack['bottleneck_signals']
            ),
            'calling_context': self._format_calling_context(
                evidence_pack['code_context']['callers']
            ),
            'constraints': self._format_constraints(
                evidence_pack['constraints']
            )
        }
        return formatted

```

#### 4.2 Tool-based Interactive Exploration

**Implementation:**

```python
class LLMToolInterface:
    def __init__(self, code_chunks, call_graph, perf_graph, vector_db):
        self.code_chunks = code_chunks
        self.call_graph = call_graph
        self.perf_graph = perf_graph
        self.vector_db = vector_db
        self.call_history = []  # Track tool calls for analysis
    
    def setup_tools(self):
        """Setup function calling tools for LLM"""
        tools = [
            {
                "name": "get_function_code",
                "description": "Get the source code and performance metrics for a function",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "function_id": {
                            "type": "string",
                            "description": "The function identifier (e.g., 'module.Class.method')"
                        }
                    },
                    "required": ["function_id"]
                }
            },
            {
                "name": "get_performance_neighborhood",
                "description": "Get functions that significantly impact the target's performance",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "function_id": {"type": "string"},
                        "threshold": {
                            "type": "number",
                            "description": "Minimum contribution threshold (0-1)",
                            "default": 0.05
                        }
                    },
                    "required": ["function_id"]
                }
            },
            {
                "name": "find_similar_patterns",
                "description": "Find similar code patterns in the codebase",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code_pattern": {
                            "type": "string",
                            "description": "Code snippet to search for similar patterns"
                        },
                        "max_results": {
                            "type": "integer",
                            "default": 5
                        }
                    },
                    "required": ["code_pattern"]
                }
            },
            {
                "name": "simulate_optimization",
                "description": "Estimate the impact of an optimization",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "function_id": {"type": "string"},
                        "optimization_type": {
                            "type": "string",
                            "enum": ["caching", "parallelization", "algorithm", "io_batching"]
                        }
                    },
                    "required": ["function_id", "optimization_type"]
                }
            }
        ]
        return tools
    
    def execute_tool_call(self, tool_name, parameters):
        """Execute a tool call from the LLM"""
        # Log the call
        self.call_history.append({
            'tool': tool_name,
            'parameters': parameters,
            'timestamp': datetime.now()
        })
        
        if tool_name == "get_function_code":
            return self._get_function_code(parameters['function_id'])
        
        elif tool_name == "get_performance_neighborhood":
            return self._get_performance_neighborhood(
                parameters['function_id'],
                parameters.get('threshold', 0.05)
            )
        
        elif tool_name == "find_similar_patterns":
            return self._find_similar_patterns(
                parameters['code_pattern'],
                parameters.get('max_results', 5)
            )
        
        elif tool_name == "simulate_optimization":
            return self._simulate_optimization(
                parameters['function_id'],
                parameters['optimization_type']
            )
        
        else:
            return {"error": f"Unknown tool: {tool_name}"}
    
    def _find_similar_patterns(self, code_pattern, max_results):
        """Find similar code patterns using vector search"""
        # Embed the pattern
        pattern_embedding = embed_code(code_pattern)
        
        # Search in vector DB
        results = self.vector_db.similarity_search(
            pattern_embedding,
            k=max_results
        )
        
        similar_patterns = []
        for result in results:
            chunk = self.code_chunks[result['id']]
            similar_patterns.append({
                'function_id': result['id'],
                'similarity_score': result['score'],
                'code_preview': chunk.code[:200] + '...' if len(chunk.code) > 200 else chunk.code,
                'performance_metrics': {
                    'execution_time': chunk.performance_fingerprint.execution_time,
                    'complexity': chunk.complexity_metrics['cyclomatic']
                }
            })
        
        return similar_patterns
    
    def _simulate_optimization(self, function_id, optimization_type):
        """Estimate optimization impact based on fingerprint"""
        chunk = self.code_chunks[function_id]
        fingerprint = chunk.performance_fingerprint
        
        estimates = {
            "caching": {
                "applicable": fingerprint.cache_efficiency > 0.2,
                "estimated_speedup": 1.0 / (1.0 - fingerprint.cache_efficiency) if fingerprint.cache_efficiency > 0 else 1.0,
                "memory_cost_mb": fingerprint.cache_efficiency * 100  # Rough estimate
            },
            "parallelization": {
                "applicable": fingerprint.parallelization_score > 0.6,
                "estimated_speedup": min(4.0, fingerprint.parallelization_score * 4),  # Assume 4 cores
                "implementation_complexity": "medium" if fingerprint.parallelization_score > 0.8 else "high"
            },
            "algorithm": {
                "applicable": chunk.complexity_metrics['cyclomatic'] > 10,
                "estimated_speedup": chunk.complexity_metrics['cyclomatic'] / 5,  # Heuristic
                "risk_level": "high" if chunk.complexity_metrics['cyclomatic'] > 20 else "medium"
            }
        }
        
        return estimates.get(optimization_type, {"error": "Unknown optimization type"})
```

#### 4.3 Transformation Plan Generation

**Implementation:**

```python
class TransformationPlanParser:
    def __init__(self):
        self.validation_rules = self._setup_validation_rules()

    def parse_llm_response(self, llm_response):
        """Parse and validate LLM's transformation plan"""
        try:
            # Extract JSON from response
            plan_json = self._extract_json(llm_response)

            # Validate structure
            validated_plan = self._validate_plan(plan_json)

            # Enhance with metadata
            enhanced_plan = self._enhance_plan(validated_plan)

            return enhanced_plan

        except Exception as e:
            return {
                "error": str(e),
                "raw_response": llm_response
            }

    def _extract_json(self, response):
        """Extract JSON from LLM response"""
        import re
        import json

        # Look for JSON block in response
        json_pattern = r'```json\n(.*?)\n```'
        matches = re.findall(json_pattern, response, re.DOTALL)

        if matches:
            return json.loads(matches[0])

        # Try to parse entire response as JSON
        try:
            return json.loads(response)
        except:
            # Fallback: try to extract JSON-like structure
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(response[json_start:json_end])

        raise ValueError("No valid JSON found in response")

    def _validate_plan(self, plan):
        """Validate transformation plan structure"""
        required_fields = ['reasoning', 'transformations']

        for field in required_fields:
            if field not in plan:
                raise ValueError(f"Missing required field: {field}")

        # Validate each transformation
        for i, transform in enumerate(plan['transformations']):
            self._validate_transformation(transform, i)

        return plan

    def _validate_transformation(self, transform, index):
        """Validate individual transformation"""
        valid_types = [
            'REPLACE_FUNCTION', 'ADD_DECORATOR', 'EXTRACT_FUNCTION',
            'ADD_IMPORT', 'MODIFY_LINES', 'ADD_FUNCTION', 'DELETE_FUNCTION'
        ]

        if 'type' not in transform:
            raise ValueError(f"Transformation {index} missing 'type'")

        if transform['type'] not in valid_types:
            raise ValueError(f"Invalid transformation type: {transform['type']}")

        # Type-specific validation
        if transform['type'] == 'REPLACE_FUNCTION':
            required = ['target', 'new_implementation']
            for field in required:
                if field not in transform:
                    raise ValueError(f"REPLACE_FUNCTION missing {field}")

        # Add more type-specific validations...

    def _enhance_plan(self, plan):
        """Add metadata and risk assessment to plan"""
        plan['metadata'] = {
            'generated_at': datetime.now().isoformat(),
            'risk_assessment': self._assess_risk(plan),
            'estimated_complexity': self._estimate_complexity(plan),
            'affects_interface': self._check_interface_changes(plan)
        }
        return plan

    def _assess_risk(self, plan):
        """Assess risk level of transformations"""
        risk_scores = {
            'ADD_DECORATOR': 1,  # Low risk
            'ADD_IMPORT': 1,
            'MODIFY_LINES': 2,  # Medium risk
            'REPLACE_FUNCTION': 3,  # Higher risk
            'EXTRACT_FUNCTION': 3,
            'DELETE_FUNCTION': 4  # Highest risk
        }

        max_risk = max(risk_scores.get(t['type'], 2) for t in plan['transformations'])

        risk_levels = {1: 'low', 2: 'medium', 3: 'high', 4: 'very_high'}
        return risk_levels.get(max_risk, 'unknown')
```

### Phase 5: Transformation & Validation

#### 5.1 AST-based Code Transformation

**Implementation:**

```python
import ast
import astor
from typing import Dict, List, Any


class ASTTransformer:
    def __init__(self, code_chunks):
        self.code_chunks = code_chunks
        self.transformations_applied = []

    def apply_transformation_plan(self, plan: Dict[str, Any]) -> Dict[str, str]:
        """Apply all transformations in the plan"""
        modified_files = {}

        for transformation in plan['transformations']:
            try:
                result = self._apply_single_transformation(transformation)

                # Track which files were modified
                for file_path, new_content in result.items():
                    modified_files[file_path] = new_content

                # Log successful transformation
                self.transformations_applied.append({
                    'type': transformation['type'],
                    'target': transformation.get('target', 'unknown'),
                    'status': 'success'
                })

            except Exception as e:
                # Log failed transformation
                self.transformations_applied.append({
                    'type': transformation['type'],
                    'target': transformation.get('target', 'unknown'),
                    'status': 'failed',
                    'error': str(e)
                })
                raise

        return modified_files

    def _apply_single_transformation(self, transformation: Dict) -> Dict[str, str]:
        """Apply a single transformation"""

        if transformation['type'] == 'REPLACE_FUNCTION':
            return self._replace_function(
                transformation['target'],
                transformation['new_implementation'],
                transformation.get('preserve_signature', True)
            )

        elif transformation['type'] == 'ADD_DECORATOR':
            return self._add_decorator(
                transformation['target'],
                transformation['decorator']
            )

        elif transformation['type'] == 'EXTRACT_FUNCTION':
            return self._extract_function(
                transformation['from'],
                transformation['new_function'],
                transformation['lines']
            )

        elif transformation['type'] == 'ADD_IMPORT':
            return self._add_import(
                transformation['target_file'],
                transformation['import_statement']
            )

        # Add more transformation types...

        else:
            raise ValueError(f"Unknown transformation type: {transformation['type']}")

    def _replace_function(self, target_id: str, new_code: str, preserve_signature: bool):
        """Replace a function with new implementation"""

        # Get the original function
        chunk = self.code_chunks[target_id]
        file_path = chunk.file_path

        # Read the entire file
        with open(file_path, 'r') as f:
            file_content = f.read()

        # Parse both file and new function
        file_ast = ast.parse(file_content)
        new_func_ast = ast.parse(new_code).body[0]

        # Find and replace the function
        replacer = FunctionReplacer(target_id, new_func_ast, preserve_signature)
        modified_ast = replacer.visit(file_ast)

        # Convert back to code
        modified_code = astor.to_source(modified_ast)

        return {file_path: modified_code}

    def _add_decorator(self, target_id: str, decorator: str):
        """Add a decorator to a function"""

        chunk = self.code_chunks[target_id]
        file_path = chunk.file_path

        with open(file_path, 'r') as f:
            file_content = f.read()

        file_ast = ast.parse(file_content)

        # Create decorator AST node
        if decorator.startswith('@'):
            decorator = decorator[1:]

        decorator_ast = ast.parse(decorator).body[0].value

        # Find function and add decorator
        decorator_adder = DecoratorAdder(target_id, decorator_ast)
        modified_ast = decorator_adder.visit(file_ast)

        modified_code = astor.to_source(modified_ast)

        return {file_path: modified_code}


class FunctionReplacer(ast.NodeTransformer):
    """AST transformer to replace functions"""

    def __init__(self, target_id: str, new_func_ast: ast.Node, preserve_signature: bool):
        self.target_id = target_id
        self.new_func_ast = new_func_ast
        self.preserve_signature = preserve_signature
        self.target_parts = target_id.split('.')

    def visit_FunctionDef(self, node):
        # Check if this is our target function
        if self._is_target_function(node):
            if self.preserve_signature:
                # Keep original signature, replace only body
                node.body = self.new_func_ast.body
                return node
            else:
                # Replace entire function
                return self.new_func_ast

        return self.generic_visit(node)

    def _is_target_function(self, node):
        # Simple name matching (extend for full path matching)
        function_name = self.target_parts[-1]
        return node.name == function_name


class DecoratorAdder(ast.NodeTransformer):
    """AST transformer to add decorators"""

    def __init__(self, target_id: str, decorator_ast: ast.Node):
        self.target_id = target_id
        self.decorator_ast = decorator_ast
        self.target_parts = target_id.split('.')

    def visit_FunctionDef(self, node):
        if self._is_target_function(node):
            # Add decorator to the function
            node.decorator_list.append(self.decorator_ast)

        return self.generic_visit(node)

    def _is_target_function(self, node):
        function_name = self.target_parts[-1]
        return node.name == function_name
```

#### 5.2 Syntax & Type Validation

**Implementation:**

```python
class CodeValidator:
    def __init__(self):
        self.validation_results = {}

    def validate_syntax(self, file_path: str, code: str) -> Dict:
        """Validate Python syntax"""
        try:
            compile(code, file_path, 'exec')
            return {'valid': True}
        except SyntaxError as e:
            return {
                'valid': False,
                'error': str(e),
                'line': e.lineno,
                'offset': e.offset
            }

    def validate_types(self, file_path: str, code: str) -> Dict:
        """Validate type hints using mypy"""
        import subprocess
        import tempfile

        # Write code to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            # Run mypy
            result = subprocess.run(
                ['mypy', '--ignore-missing-imports', temp_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            return {
                'valid': result.returncode == 0,
                'output': result.stdout,
                'errors': result.stderr
            }

        finally:
            os.unlink(temp_path)

    def validate_imports(self, code: str) -> Dict:
        """Check if all imports are valid"""
        tree = ast.parse(code)

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}")

        # Check if imports are available
        missing_imports = []
        for imp in imports:
            try:
                __import__(imp.split('.')[0])
            except ImportError:
                missing_imports.append(imp)

        return {
            'valid': len(missing_imports) == 0,
            'missing_imports': missing_imports
        }
```

#### 5.3 Test Suite Execution

**Implementation:**

```python
class TestRunner:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.test_framework = self._detect_test_framework()

    def _detect_test_framework(self):
        """Detect which test framework is used"""
        # Check for test files
        test_files = list(self.project_path.glob('**/test_*.py')) +
                     list(self.project_path.glob('**/*_test.py'))

        if not test_files:
            return None

        # Check imports in test files
        for test_file in test_files[:5]:  # Sample first 5
            with open(test_file, 'r') as f:
                content = f.read()
                if 'import pytest' in content or 'from pytest' in content:
                    return 'pytest'
                elif 'import unittest' in content:
                    return 'unittest'
                elif 'import nose' in content:
                    return 'nose'

        return 'unittest'  # Default

    def run_tests(self, modified_files: Dict[str, str]) -> Dict:
        """Run test suite with modified files"""
        import subprocess
        import tempfile
        import shutil

        # Create temporary directory with modified files
        with tempfile.TemporaryDirectory() as temp_dir:
            # Copy entire project
            temp_project = Path(temp_dir) / 'project'
            shutil.copytree(self.project_path, temp_project)

            # Apply modifications
            for file_path, new_content in modified_files.items():
                full_path = temp_project / file_path
                with open(full_path, 'w') as f:
                    f.write(new_content)

            # Run tests
            return self._execute_tests(temp_project)

    def _execute_tests(self, project_path: Path) -> Dict:
        """Execute test suite"""

        if self.test_framework == 'pytest':
            cmd = ['pytest', str(project_path), '-v', '--tb=short']
        elif self.test_framework == 'unittest':
            cmd = ['python', '-m', 'unittest', 'discover', str(project_path)]
        else:
            return {'status': 'no_tests', 'passed': True}

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(project_path)
        )

        return {
            'status': 'completed',
            'passed': result.returncode == 0,
            'output': result.stdout,
            'errors': result.stderr,
            'return_code': result.returncode
        }
```

#### 5.4 Performance Benchmarking

**Implementation:**

```python
class PerformanceBenchmark:
    def __init__(self, benchmark_suite: List[Dict]):
        self.benchmark_suite = benchmark_suite
        self.results = {}

    def run_benchmark(self, original_code: str, optimized_code: str,
                      function_id: str) -> Dict:
        """Run performance comparison between original and optimized"""

        # Setup benchmark environment
        benchmark_env = self._setup_benchmark_env(original_code, optimized_code)

        # Run benchmarks
        original_results = self._run_single_benchmark(
            benchmark_env['original'],
            function_id
        )

        optimized_results = self._run_single_benchmark(
            benchmark_env['optimized'],
            function_id
        )

        # Calculate speedup
        speedup = self._calculate_speedup(original_results, optimized_results)

        # Statistical significance test
        significance = self._test_significance(original_results, optimized_results)

        return {
            'original': original_results,
            'optimized': optimized_results,
            'speedup': speedup,
            'significant': significance['significant'],
            'confidence': significance['confidence'],
            'details': {
                'samples': len(original_results['times']),
                'original_mean': original_results['mean'],
                'optimized_mean': optimized_results['mean'],
                'relative_speedup': original_results['mean'] / optimized_results['mean']
            }
        }

    def _run_single_benchmark(self, code_module, function_id) -> Dict:
        """Run benchmark for a single version"""
        import timeit
        import statistics

        # Extract function name
        func_name = function_id.split('.')[-1]

        # Prepare benchmark code
        setup = f"from {code_module} import {func_name}"

        # Find appropriate benchmark inputs
        benchmark_inputs = self._get_benchmark_inputs(function_id)

        times = []
        memory_usage = []

        for inputs in benchmark_inputs:
            # Time execution
            stmt = f"{func_name}({inputs})"

            # Run multiple times for statistical validity
            exec_times = timeit.repeat(
                stmt,
                setup=setup,
                repeat=10,
                number=100
            )

            times.extend(exec_times)

            # Measure memory (simplified)
            import tracemalloc
            tracemalloc.start()
            exec(f"{setup}; {stmt}")
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            memory_usage.append(peak)

        return {
            'times': times,
            'mean': statistics.mean(times),
            'median': statistics.median(times),
            'stdev': statistics.stdev(times) if len(times) > 1 else 0,
            'memory_peak': max(memory_usage),
            'memory_mean': statistics.mean(memory_usage)
        }

    def _calculate_speedup(self, original: Dict, optimized: Dict) -> float:
        """Calculate speedup factor"""
        if optimized['mean'] == 0:
            return float('inf')

        return original['mean'] / optimized['mean']

    def _test_significance(self, original: Dict, optimized: Dict) -> Dict:
        """Test statistical significance of improvement"""
        from scipy import stats

        # Perform t-test
        t_stat, p_value = stats.ttest_ind(
            original['times'],
            optimized['times'],
            equal_var=False  # Welch's t-test
        )

        # Calculate effect size (Cohen's d)
        pooled_std = ((original['stdev'] ** 2 + optimized['stdev'] ** 2) / 2) ** 0.5
        effect_size = (original['mean'] - optimized['mean']) / pooled_std if pooled_std > 0 else 0

        return {
            'significant': p_value < 0.05,
            'p_value': p_value,
            'effect_size': effect_size,
            'confidence': 1 - p_value
        }
```

### Phase 6: Version Management & Decision

#### 6.1 Version Graph Update

**Implementation:**

```python
import uuid
from datetime import datetime
from typing import Dict, List, Optional
import pickle


class VersionNode:
    def __init__(self, version_id: str = None):
        self.version_id = version_id or str(uuid.uuid4())
        self.timestamp = datetime.now()
        self.function_versions: Dict[str, str] = {}  # function_id -> code
        self.performance_metrics: Dict = {}
        self.transformation_applied: Optional[Dict] = None
        self.parent_version: Optional[str] = None
        self.children_versions: List[str] = []
        self.status: str = 'pending'  # pending, tested, accepted, rejected


class VersionGraph:
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.nodes: Dict[str, VersionNode] = {}
        self.current_version: Optional[str] = None
        self.base_version: Optional[str] = None

        # Load existing graph if available
        self._load_graph()

    def create_base_version(self, code_chunks: Dict[str, CodeChunk]) -> str:
        """Create initial version from original code"""
        node = VersionNode()

        # Store original code for all functions
        for chunk_id, chunk in code_chunks.items():
            node.function_versions[chunk_id] = chunk.code

        node.status = 'accepted'
        self.base_version = node.version_id
        self.current_version = node.version_id
        self.nodes[node.version_id] = node

        self._save_graph()
        return node.version_id

    def apply_transformation(self, transformation_plan: Dict,
                             modified_code: Dict[str, str]) -> VersionNode:
        """Create new version with transformation applied"""

        # Create new node
        new_node = VersionNode()
        new_node.parent_version = self.current_version
        new_node.transformation_applied = transformation_plan

        # Copy function versions from parent
        parent_node = self.nodes[self.current_version]
        new_node.function_versions = parent_node.function_versions.copy()

        # Apply modifications
        for function_id, new_code in modified_code.items():
            new_node.function_versions[function_id] = new_code

        # Add to graph
        self.nodes[new_node.version_id] = new_node
        parent_node.children_versions.append(new_node.version_id)

        self._save_graph()
        return new_node

    def update_performance_metrics(self, version_id: str, metrics: Dict):
        """Update performance metrics for a version"""
        if version_id in self.nodes:
            self.nodes[version_id].performance_metrics = metrics
            self._save_graph()

    def accept_version(self, version_id: str):
        """Mark version as accepted and make it current"""
        if version_id in self.nodes:
            self.nodes[version_id].status = 'accepted'
            self.current_version = version_id
            self._save_graph()

    def reject_version(self, version_id: str, reason: str = None):
        """Mark version as rejected"""
        if version_id in self.nodes:
            self.nodes[version_id].status = 'rejected'
            if reason:
                self.nodes[version_id].rejection_reason = reason
            self._save_graph()

    def rollback(self, version_id: str = None):
        """Rollback to specific version or parent"""
        if version_id and version_id in self.nodes:
            self.current_version = version_id
        elif self.current_version:
            current_node = self.nodes[self.current_version]
            if current_node.parent_version:
                self.current_version = current_node.parent_version

        self._save_graph()
        return self.current_version

    def get_improvement_path(self) -> List[VersionNode]:
        """Get path of successful optimizations from base to current"""
        path = []
        current = self.current_version

        while current:
            node = self.nodes[current]
            if node.status == 'accepted':
                path.append(node)
            current = node.parent_version

        path.reverse()
        return path

    def get_version_code(self, version_id: str) -> Dict[str, str]:
        """Get all code for a specific version"""
        if version_id in self.nodes:
            return self.nodes[version_id].function_versions
        return {}

    def _save_graph(self):
        """Persist graph to disk"""
        graph_file = self.storage_path / 'version_graph.pkl'
        with open(graph_file, 'wb') as f:
            pickle.dump({
                'nodes': self.nodes,
                'current_version': self.current_version,
                'base_version': self.base_version
            }, f)

    def _load_graph(self):
        """Load graph from disk"""
        graph_file = self.storage_path / 'version_graph.pkl'
        if graph_file.exists():
            with open(graph_file, 'rb') as f:
                data = pickle.load(f)
                self.nodes = data['nodes']
                self.current_version = data['current_version']
                self.base_version = data['base_version']
```

#### 6.2 Statistical Significance Testing

Already implemented in section 5.4 with the `_test_significance` method.

#### 6.3 Commit or Rollback Decision

**Implementation:**

```python
class OptimizationDecisionMaker:
    def __init__(self, version_graph: VersionGraph,
                 min_speedup: float = 1.1,
                 confidence_threshold: float = 0.95):
        self.version_graph = version_graph
        self.min_speedup = min_speedup
        self.confidence_threshold = confidence_threshold

    def make_decision(self, version_id: str, test_results: Dict,
                      benchmark_results: Dict) -> Dict:
        """Decide whether to accept or reject optimization"""

        decision = {
            'version_id': version_id,
            'timestamp': datetime.now().isoformat(),
            'accept': False,
            'reasons': []
        }

        # Check test results
        if not test_results.get('passed', False):
            decision['reasons'].append('Tests failed')
            self.version_graph.reject_version(version_id, 'Tests failed')
            return decision

        # Check performance improvement
        speedup = benchmark_results.get('speedup', 1.0)
        if speedup < self.min_speedup:
            decision['reasons'].append(f'Insufficient speedup: {speedup:.2f}x < {self.min_speedup}x')
            self.version_graph.reject_version(version_id, 'Insufficient speedup')
            return decision

        # Check statistical significance
        if not benchmark_results.get('significant', False):
            decision['reasons'].append('Performance improvement not statistically significant')
            self.version_graph.reject_version(version_id, 'Not significant')
            return decision

        # Check confidence level
        confidence = benchmark_results.get('confidence', 0)
        if confidence < self.confidence_threshold:
            decision['reasons'].append(f'Low confidence: {confidence:.2%} < {self.confidence_threshold:.2%}')
            self.version_graph.reject_version(version_id, 'Low confidence')
            return decision

        # All checks passed - accept
        decision['accept'] = True
        decision['reasons'].append(f'Optimization accepted: {speedup:.2f}x speedup with {confidence:.2%} confidence')

        # Update version graph
        self.version_graph.update_performance_metrics(version_id, benchmark_results)
        self.version_graph.accept_version(version_id)

        return decision
```

### Phase 7: Evaluation Metrics Collection

#### 7.1 Performance Uplift Calculation

**Implementation:**

```python
class PerformanceAnalyzer:
    def __init__(self, version_graph: VersionGraph):
        self.version_graph = version_graph

    def calculate_cumulative_uplift(self) -> Dict:
        """Calculate total performance improvement"""

        path = self.version_graph.get_improvement_path()

        if len(path) < 2:
            return {'total_speedup': 1.0, 'optimizations': 0}

        base_version = path[0]
        current_version = path[-1]

        # Get performance metrics
        base_metrics = base_version.performance_metrics
        current_metrics = current_version.performance_metrics

        # Calculate overall speedup
        if base_metrics and current_metrics:
            total_speedup = current_metrics.get('speedup', 1.0)
        else:
            total_speedup = 1.0

        # Analyze per-optimization impact
        optimization_impacts = []
        for i in range(1, len(path)):
            prev = path[i - 1]
            curr = path[i]

            if curr.transformation_applied:
                impact = {
                    'version': curr.version_id,
                    'transformation': curr.transformation_applied.get('type', 'unknown'),
                    'speedup': curr.performance_metrics.get('speedup', 1.0),
                    'bottleneck_type': curr.transformation_applied.get('bottleneck_type', 'unknown')
                }
                optimization_impacts.append(impact)

        return {
            'total_speedup': total_speedup,
            'optimizations': len(optimization_impacts),
            'optimization_impacts': optimization_impacts,
            'improvement_path': [node.version_id for node in path]
        }
```

#### 7.2 LLM Comparison Metrics

**Implementation:**

```python
class LLMComparison:
    def __init__(self):
        self.results = {}

    def record_llm_performance(self, llm_name: str, bottleneck_type: str,
                               metrics: Dict):
        """Record performance metrics for an LLM"""

        if llm_name not in self.results:
            self.results[llm_name] = {}

        if bottleneck_type not in self.results[llm_name]:
            self.results[llm_name][bottleneck_type] = []

        self.results[llm_name][bottleneck_type].append(metrics)

    def generate_comparison_report(self) -> Dict:
        """Generate comprehensive comparison report"""

        report = {}

        for llm_name, bottleneck_results in self.results.items():
            llm_stats = {}

            for bottleneck_type, metrics_list in bottleneck_results.items():
                # Calculate statistics per bottleneck type
                stats = {
                    'detection_rate': self._calculate_detection_rate(metrics_list),
                    'fix_success_rate': self._calculate_fix_success_rate(metrics_list),
                    'average_speedup': self._calculate_average_speedup(metrics_list),
                    'average_attempts': self._calculate_average_attempts(metrics_list),
                    'tool_usage': self._analyze_tool_usage(metrics_list)
                }
                llm_stats[bottleneck_type] = stats

            # Calculate overall statistics
            llm_stats['overall'] = self._calculate_overall_stats(bottleneck_results)

            report[llm_name] = llm_stats

        return report

    def _calculate_detection_rate(self, metrics_list: List[Dict]) -> float:
        """Calculate bottleneck detection rate"""
        detected = sum(1 for m in metrics_list if m.get('detected', False))
        return detected / len(metrics_list) if metrics_list else 0

    def _calculate_fix_success_rate(self, metrics_list: List[Dict]) -> float:
        """Calculate successful fix rate"""
        successful = sum(1 for m in metrics_list if m.get('fix_successful', False))
        detected = sum(1 for m in metrics_list if m.get('detected', False))
        return successful / detected if detected > 0 else 0

    def _calculate_average_speedup(self, metrics_list: List[Dict]) -> float:
        """Calculate average speedup achieved"""
        speedups = [m.get('speedup', 1.0) for m in metrics_list
                    if m.get('fix_successful', False)]
        return sum(speedups) / len(speedups) if speedups else 1.0

    def _calculate_average_attempts(self, metrics_list: List[Dict]) -> float:
        """Calculate average number of attempts needed"""
        attempts = [m.get('attempts', 1) for m in metrics_list]
        return sum(attempts) / len(attempts) if attempts else 0

    def _analyze_tool_usage(self, metrics_list: List[Dict]) -> Dict:
        """Analyze how LLMs use available tools"""
        tool_usage = {}

        for metrics in metrics_list:
            for tool_call in metrics.get('tool_calls', []):
                tool_name = tool_call['tool']
                tool_usage[tool_name] = tool_usage.get(tool_name, 0) + 1

        return tool_usage
```

#### 7.3 Bottleneck-specific Success Analysis

**Implementation:**

```python
class BottleneckAnalysis:
    def __init__(self, results: Dict):
        self.results = results

    def analyze_bottleneck_patterns(self) -> Dict:
        """Analyze which bottleneck types are easiest/hardest to fix"""

        analysis = {}

        bottleneck_types = [
            'algorithmic_complexity',
            'caching_opportunities',
            'memory_inefficiency',
            'unused_parallelism',
            'synchronous_io'
        ]

        for bottleneck_type in bottleneck_types:
            type_results = self._collect_results_for_type(bottleneck_type)

            analysis[bottleneck_type] = {
                'total_instances': len(type_results),
                'detection_rate': self._calc_detection_rate(type_results),
                'fix_rate': self._calc_fix_rate(type_results),
                'average_speedup': self._calc_avg_speedup(type_results),
                'common_failures': self._identify_failure_patterns(type_results),
                'best_performing_llm': self._find_best_llm(type_results),
                'typical_transformation': self._find_common_transformation(type_results)
            }

        return analysis

    def generate_insights(self, analysis: Dict) -> List[str]:
        """Generate actionable insights from analysis"""

        insights = []

        # Find easiest bottleneck type to fix
        easiest = max(analysis.items(),
                      key=lambda x: x[1]['fix_rate'])
        insights.append(
            f"Easiest to fix: {easiest[0]} with {easiest[1]['fix_rate']:.1%} success rate"
        )

        # Find highest impact bottleneck
        highest_impact = max(analysis.items(),
                             key=lambda x: x[1]['average_speedup'])
        insights.append(
            f"Highest impact: {highest_impact[0]} with {highest_impact[1]['average_speedup']:.2f}x average speedup"
        )

        # Find bottleneck with most room for improvement
        lowest_detection = min(analysis.items(),
                               key=lambda x: x[1]['detection_rate'])
        insights.append(
            f"Needs improvement: {lowest_detection[0]} detection rate only {lowest_detection[1]['detection_rate']:.1%}"
        )

        return insights
```

This completes the detailed implementation guide for the PEARL system. Each component has been thoroughly specified with
concrete implementation approaches, libraries to use, and algorithms to employ. The system is designed to be
implementable by a single person while maintaining sophistication and novelty suitable for a master's thesis.