# PEARL: Performance Evidence-Augmented Refactoring with LLMs
## Complete Architectural Specification - Detailed Implementation Guide

---

## 1. System Overview and Philosophy

### 1.1 Core Objective

PEARL is a framework designed to automatically identify and fix performance bottlenecks in Python code by combining static analysis, dynamic profiling, and Large Language Model reasoning. The system operates on the principle that performance optimization requires both quantitative evidence (profiling data) and qualitative understanding (code semantics), which LLMs can bridge.

### 1.2 Key Innovation Points

The system introduces several novel concepts:

1. **Performance Fingerprints**: Multi-dimensional characterizations of function behavior combining static code properties with dynamic runtime metrics
2. **Evidence-Based Bottleneck Detection**: Systematic identification of optimization opportunities based on measurable criteria rather than heuristics alone
3. **Targeted Code Exploration**: The LLM examines code only after analyzing performance metrics, preventing unfocused exploration
4. **Bottleneck Hypothesis Generation**: The LLM forms hypotheses about performance issues before seeing code, ensuring systematic analysis

### 1.3 System Architecture Flow

The system operates in three major phases:

1. **Analysis Phase**: Extract all possible information about the codebase through static analysis and dynamic profiling
2. **Optimization Phase**: Use LLM reasoning to identify bottlenecks and generate fixes
3. **Validation Phase**: Test and benchmark proposed changes

---

## 2. Phase 1: Code Analysis Pipeline

### 2.1 Project Discovery and Setup

#### 2.1.1 Initial Project Scanning

The system begins by discovering the complete structure of the target Python project. This involves:

**Directory Traversal Process:**
- Start from the project root directory
- Recursively scan all subdirectories
- Identify Python files by the `.py` extension
- Create a file manifest containing full paths to all Python files

**Package Structure Detection:**
- Identify Python packages by locating `__init__.py` files
- Build a hierarchy map showing package relationships
- Determine the import structure (which modules can import which others)
- Identify the main entry points by looking for `if __name__ == "__main__"` blocks

**Dependency Analysis:**
- Parse `requirements.txt`, `setup.py`, `pyproject.toml`, or `Pipfile` to identify external dependencies
- Create a dependency map showing which external libraries are used
- Verify that all dependencies are installed in the current environment
- Note version constraints for reproducibility

**Test Infrastructure Discovery:**
- Locate test files following common patterns: `test_*.py`, `*_test.py`, or files in `tests/` directories
- Identify the testing framework by examining imports (pytest, unittest, nose)
- Determine test execution commands needed for later validation
- Map which test files test which source files (through imports or naming conventions)

#### 2.1.2 Environment Preparation

**Isolation Setup:**
- Create a virtual environment specifically for profiling to avoid contamination
- Install all project dependencies in this environment
- Verify that the project can be imported and basic imports work
- Set up CPU affinity and disable frequency scaling for consistent profiling

### 2.2 Static Code Analysis

#### 2.2.1 AST Parsing and Code Chunking

**Parsing Process:**

For each Python file in the manifest:
1. Read the file content as text
2. Parse into an Abstract Syntax Tree using Python's ast module
3. Walk the tree to identify all relevant nodes

**Function Extraction:**

For each function definition found:
- Extract the complete function source code preserving formatting
- Capture the function signature including parameter names, defaults, and type hints
- Extract decorators as a list of decorator names and their arguments
- Capture the docstring if present (first string constant in the function body)
- Record the exact line numbers where the function starts and ends
- Note whether it's a standalone function, method, static method, or class method

**Class Extraction:**

For each class definition:
- Extract the class definition including all methods
- Capture inheritance relationships (base classes)
- Identify class-level attributes and their initial values
- Record which methods belong to the class
- Note special methods (`__init__`, `__str__`, etc.)

**Module-Level Analysis:**
- Extract all import statements and their types (import vs from-import)
- Identify module-level constants and global variables
- Record module docstring if present
- Note any module-level code that executes on import

**Unique Identifier Generation:**

Each code chunk receives a Fully Qualified Name (FQN):
- Format: `package.module.ClassName.method_name` or `package.module.function_name`
- This serves as a unique identifier throughout the system
- Store bidirectional mapping between FQN and file location

#### 2.2.2 Complexity Metrics Calculation

**Cyclomatic Complexity:**

For each function, calculate the cyclomatic complexity:
- Start with a base complexity of 1
- Add 1 for each: if, elif, for, while, except, with statement
- Add 1 for each boolean operator (and, or) in conditions
- Add 1 for each case in match statements (Python 3.10+)
- The result indicates the number of independent paths through the function

**Cognitive Complexity:**

A more sophisticated metric that considers:
- Nesting depth (nested conditions are harder to understand)
- Complexity of conditions (chained boolean operations)
- Early returns and breaks (which can simplify or complicate flow)
- Recursion (adds significant cognitive load)

Calculate by:
- Start with 0
- Add 1 for each control flow statement
- Add nesting depth as additional penalty for nested structures
- Add extra penalty for recursive calls

**Lines of Code Metrics:**
- Total Lines (LOC): Count all lines including blanks and comments
- Source Lines of Code (SLOC): Count only lines with actual code
- Comment Lines: Count lines that are comments
- Blank Lines: Count empty lines
- Code-to-Comment Ratio: SLOC / Comment Lines

**Additional Structural Metrics:**
- Parameter Count: Number of function parameters
- Return Points: Number of return statements
- Variable Count: Number of unique variables used
- Maximum Nesting Depth: Deepest level of nested blocks

#### 2.2.3 Static Call Graph Construction

**Call Relationship Extraction:**

For each function:
1. Identify all function calls within its body
2. Resolve each call to its target function if possible
3. Handle different call types:
   - Direct function calls: `function_name()`
   - Method calls: `object.method()`
   - Static/class method calls: `ClassName.method()`
   - Dynamic calls: Store as "unresolved" with possible targets

**Call Graph Building:**

Create a directed graph where:
- Nodes represent functions (identified by FQN)
- Edges represent "calls" relationships
- Edge weights initially set to 1 (will be updated with dynamic data)
- Store both forward edges (caller → callee) and reverse edges (callee → callers)

**Call Graph Analysis:**

Calculate graph properties:
- In-degree: Number of functions that call this function
- Out-degree: Number of functions this function calls
- Strongly connected components: Groups of mutually recursive functions
- Call depth: Maximum depth from entry points to this function

#### 2.2.4 Loop and Control Flow Analysis

**Loop Detection and Characterization:**

For each function, identify and analyze loops:

**Loop Identification:**
- Find all for loops, while loops, and list/dict/set comprehensions
- Determine loop nesting depth (loops within loops)
- Identify the iteration variable and iterable

**Loop Pattern Classification:**
- Range loops: `for i in range(n)`
- Collection iteration: `for item in collection`
- Enumeration: `for i, item in enumerate(collection)`
- Zip iteration: `for a, b in zip(list1, list2)`
- While with counter: `while i < n: i += 1`
- Infinite loops: `while True` with break conditions

**Loop Body Analysis:**
- Count statements in loop body
- Identify operations performed (arithmetic, list operations, I/O)
- Detect nested loops and their relationship
- Find loop-carried dependencies (variables modified and used across iterations)

**Iteration Count Estimation:**

For static iteration counts:
- Range with literal: `range(100)` → 100 iterations
- Collection with known size: `for item in [1,2,3]` → 3 iterations
- While with simple counter: Attempt to determine bounds

For dynamic iteration counts:
- Mark as "dynamic" with possible bounds if determinable
- Note relationship to input parameters

#### 2.2.5 Data Structure Usage Analysis

**Data Structure Operations Detection:**

Identify usage patterns for each data type:

**List Operations:**
- Append operations (O(1) amortized)
- Insert operations at arbitrary positions (O(n))
- Membership tests with 'in' (O(n))
- Index access patterns
- Slice operations

**Dictionary Operations:**
- Key access patterns
- Membership tests (O(1) average)
- Iteration over keys/values/items
- Dynamic key addition

**Set Operations:**
- Membership tests (O(1) average)
- Set operations (union, intersection)
- Add/remove patterns

**Nested Data Structures:**
- List of lists patterns
- Dictionary of lists
- Complex nesting depths

**Operation Context:**
- Whether operations occur inside loops
- Frequency of operations (from static analysis)
- Size indicators (if determinable)

### 2.3 Dynamic Profiling and Runtime Analysis

#### 2.3.1 Profiling Environment Setup

**CPU Configuration:**
- Pin the process to specific CPU cores to avoid migration
- Disable CPU frequency scaling to ensure consistent timing
- Set process priority to reduce interference
- Disable turbo boost if possible for consistency

**Memory Configuration:**
- Clear caches before profiling runs
- Ensure sufficient memory to avoid swapping
- Monitor system memory pressure during profiling

**Test Workload Preparation:**
- Identify representative workloads that exercise the code
- Ensure all planted bottlenecks are covered
- Create deterministic inputs for reproducibility
- Warm up the Python interpreter with initial runs

#### 2.3.2 Function-Level Performance Profiling

**Execution Time Profiling:**

Using a hierarchical profiler (cProfile or pyinstrument):

**Per-Function Metrics Collection:**
- Total Time (Inclusive): Time spent in function including all calls it makes
- Self Time (Exclusive): Time spent in function excluding time in called functions
- Call Count: Number of times function was called
- Average Time per Call: Total time divided by call count
- Maximum Single Call Time: Longest execution of the function
- Minimum Single Call Time: Shortest execution of the function

**Call Relationship Timing:**
- Time spent in each caller-callee relationship
- Number of calls for each relationship
- Average time per call for each relationship

**Execution Time Percentage Calculation:**
- Calculate total program execution time
- For each function, calculate exclusive time as percentage of total
- For each function, calculate inclusive time as percentage of total
- Identify cumulative percentage (top N functions accounting for X% of time)

#### 2.3.3 Line-Level Profiling

**Line Profiler Application:**

For functions identified as hotspots (>5% execution time):

**Line-by-Line Timing:**
- Time spent on each line of code
- Number of times each line was executed  
- Average time per line execution
- Identify lines that dominate function time

**Loop Body Analysis:**
- Map line numbers to loop bodies
- Calculate time spent in loop body vs loop overhead
- Identify expensive operations within loops
- Calculate average iteration time

**Branch Analysis:**
- Time spent in different conditional branches
- Frequency of branch taken vs not taken
- Cost of branch misprediction patterns

#### 2.3.4 Memory Profiling

**Memory Allocation Tracking:**

Using tracemalloc or memory_profiler:

**Per-Function Memory Metrics:**
- Memory allocated by function (bytes)
- Memory freed by function
- Net memory change
- Peak memory usage during function execution
- Number of allocations
- Average allocation size

**Allocation Patterns:**
- Identify allocation sites (file:line)
- Track allocation frequencies
- Detect memory allocation in loops
- Identify potential memory leaks

**Object Creation Tracking:**
- Count object instantiations
- Track object types created
- Identify temporary object creation
- Detect object churn patterns

#### 2.3.5 I/O Operations Profiling

**I/O Monitoring Setup:**

Instrument I/O operations by intercepting system calls:

**File I/O Tracking:**
- Number of file open/close operations
- Bytes read/written per operation
- Time spent in I/O operations
- Sequential vs random access patterns

**Network I/O Tracking:**
- Number of network requests
- Bytes sent/received
- Latency per request
- Connection pooling efficiency

**Database I/O Tracking:**
- Number of queries
- Query execution time
- Result set sizes
- Connection management overhead

#### 2.3.6 Argument Pattern Analysis

**Function Argument Tracking:**

For expensive functions, track argument patterns:

**Argument Hashing:**
- Create normalized hashes of function arguments
- Handle different argument types appropriately:
  - Primitives: Direct value comparison
  - Collections: Size and sample of contents
  - Objects: Type and key attributes
  - Large data: Shape and statistics only

**Repetition Analysis:**
- Count unique vs total argument combinations
- Calculate argument repetition rate
- Identify most common argument patterns
- Estimate cache potential

**Argument Relationship Analysis:**
- Correlation between argument values and execution time
- Argument values that trigger expensive paths
- Patterns in argument sequences

### 2.4 Performance Fingerprint Generation

#### 2.4.1 Fingerprint Components

Each function receives a comprehensive performance fingerprint containing:

**Execution Profile:**
- `execution_time_percent`: Percentage of total program time spent in this function (exclusive)
- `inclusive_time_percent`: Percentage including called functions
- `call_count`: Total number of invocations
- `avg_time_ms`: Average execution time per call in milliseconds
- `max_time_ms`: Maximum execution time observed
- `min_time_ms`: Minimum execution time observed
- `time_variance`: Variance in execution times

**Memory Profile:**
- `memory_allocated_mb`: Total memory allocated by function in megabytes
- `memory_freed_mb`: Total memory freed
- `net_memory_delta_mb`: Net change in memory
- `peak_memory_mb`: Peak memory during execution
- `allocation_count`: Number of allocation operations
- `allocation_sites`: Number of unique allocation locations

**I/O Profile:**
- `io_operations_count`: Total I/O operations
- `io_bytes_total`: Total bytes transferred
- `io_time_percent`: Percentage of function time spent in I/O
- `io_pattern`: Sequential, random, or mixed

**Loop Characteristics:**
- `loop_depth`: Maximum nesting depth of loops
- `loop_count`: Number of loop constructs
- `estimated_iterations`: Estimated total iterations across all invocations
- `iteration_variance`: Variance in iteration counts
- `loop_carried_dependencies`: Whether loops have dependencies between iterations

**Caching Potential:**
- `argument_repetition_rate`: Fraction of calls with repeated arguments
- `unique_argument_combinations`: Number of unique argument patterns
- `purity_score`: Likelihood function is pure (no side effects)
- `memoization_memory_estimate`: Estimated memory for full memoization

**Parallelization Potential:**
- `parallelization_score`: 0-1 score for parallelization suitability
- `data_dependency_score`: Degree of data dependencies
- `gil_impact_estimate`: Estimated impact of Python GIL
- `vectorization_potential`: Suitability for numpy/vector operations

**Complexity Indicators:**
- `cyclomatic_complexity`: Number of independent paths
- `cognitive_complexity`: Mental effort to understand
- `nesting_depth`: Maximum block nesting
- `variable_count`: Number of variables used

#### 2.4.2 Fingerprint Calculation Details

**Execution Time Percentage Calculation:**

1. Sum total execution time across all functions (exclusive times)
2. For each function, divide its exclusive time by total
3. Multiply by 100 for percentage
4. Functions with <0.1% are marked as "negligible"

**Memory Delta Calculation:**

1. Take memory snapshot before function entry
2. Take memory snapshot after function exit
3. Calculate difference in allocated blocks
4. Track across multiple invocations for average

**Argument Repetition Rate Calculation:**

1. For each invocation, create normalized hash of arguments
2. Count occurrences of each unique hash
3. Calculate: (total_calls - unique_hashes) / total_calls
4. Rate of 0 means all unique, 1 means all identical

**Parallelization Score Calculation:**

Start with base score of 1.0, then apply multipliers:
- Multiply by 0.3 if function has global state modifications
- Multiply by 0.5 if function has file I/O operations
- Multiply by 0.7 if function has shared mutable parameters
- Multiply by 1.2 if function is CPU-bound (CPU time ≈ wall time)
- Multiply by 1.3 if loop iterations are independent
- Cap final score between 0 and 1

**Purity Score Assessment:**

Start with assumption of purity (1.0), reduce for:
- Any I/O operations: reduce by 0.5
- Global variable access: reduce by 0.3
- Random number generation: reduce by 0.4
- Time-dependent operations: reduce by 0.4
- Object mutation: reduce by 0.2
- External API calls: reduce by 0.5

### 2.5 Data Flow and Execution Path Analysis

#### 2.5.1 Execution Hot Paths Extraction

**Critical Path Identification:**

Instead of presenting functions in isolation, identify the actual execution paths that consume the most time:

**Hot Path Detection Process:**

1. Start from program entry points (main functions, test functions)
2. Trace through the dynamic call graph using profiler data
3. For each path from entry to leaf function:
   - Sum the exclusive times of all functions in the path
   - Weight by the number of times this path is executed
   - Calculate total contribution to program runtime

4. Rank paths by total time contribution
5. Select top 3-5 paths that account for majority of runtime

**Path Representation:**

Each hot path is represented as:
- Entry point function (where execution starts)
- Sequence of function calls with timing at each step
- Terminal function (deepest in call stack)
- Total time for this path
- Percentage of program time
- Call count for this path

Example representation:
```
Path 1 (45% of runtime, called 1000 times):
main() [2ms] → process_batch() [10ms] → validate_items() [120ms] → check_syntax() [315ms]
```

This reveals that while `process_batch` appears high-level, the real bottleneck is deep in `check_syntax`.

#### 2.5.2 Data Flow Augmentation

**Input/Output Characterization:**

For each function in hot paths, characterize data flow:

**Input Characteristics:**
- Data types of parameters (primitive, collection, object)
- Collection sizes (when determinable)
- Value ranges or domains
- Whether inputs are constants, variables, or computed
- Frequency of unique vs repeated inputs

**Output Characteristics:**
- Return type and structure
- Output size relative to input
- Whether output is deterministic for given input
- Side effects beyond return value

**Data Transformation Patterns:**
- Filter: Input collection → smaller collection
- Map: Input collection → transformed collection of same size
- Reduce: Input collection → single value
- Expand: Input → larger output
- Pass-through: Input ≈ output with minor changes

**Data Flow Annotations:**

Create human-readable descriptions:
- "Function `process_records()` receives list of 10,000 items, returns filtered list of ~100 items"
- "Function `get_config()` called 1,000 times, always returns same dictionary after first call"
- "Function `validate()` receives string, returns boolean, no side effects"

These annotations bridge the gap between performance metrics and semantic understanding.

---

## 3. Phase 2: Bottleneck Detection and Evidence Assembly

### 3.1 Bottleneck Pattern Definition

#### 3.1.1 Bottleneck Categories

The system recognizes several categories of performance bottlenecks:

**Algorithmic Complexity Bottlenecks:**
- Quadratic or higher complexity algorithms where linear is possible
- Nested loops with inefficient operations
- Repeated linear searches instead of hash lookups
- Inefficient sorting or searching algorithms
- Unnecessary repeated computations

**Caching Opportunity Bottlenecks:**
- Pure functions called repeatedly with same arguments
- Expensive computations with limited input domain
- Configuration lookups that don't change
- Network/database queries for static data

**Memory Inefficiency Bottlenecks:**
- Object recreation in loops
- Unnecessary copying of large data structures
- Memory leaks from unclosed resources
- Inefficient string concatenation
- Large temporary objects

**I/O Inefficiency Bottlenecks:**
- Unbatched database queries
- Multiple small file reads/writes
- Synchronous I/O that could be async
- Missing connection pooling
- Redundant network requests

**Parallelization Opportunity Bottlenecks:**
- CPU-bound loops with independent iterations
- Embarrassingly parallel computations done serially
- Map operations that could use multiprocessing
- Independent tasks executed sequentially

**Data Structure Bottlenecks:**
- Using lists for membership testing
- Wrong collection type for access pattern
- Missing indices on frequently accessed data
- Inefficient data representations

#### 3.1.2 Bottleneck Detection Rules

Each bottleneck type has specific detection criteria based on fingerprint values:

**Algorithmic Complexity Detection:**
- Cyclomatic complexity > 10 AND
- Loop nesting depth ≥ 2 AND
- Execution time percentage > 5% AND
- Line profiler shows inner loop dominating time

**Caching Opportunity Detection:**
- Argument repetition rate > 0.3 AND
- Call count > 100 AND
- Purity score > 0.7 AND
- No detected side effects

**Memory Inefficiency Detection:**
- Memory allocation in loops AND
- Net memory delta > 10MB OR
- Allocation count > 10000 AND
- Object churn detected in line profiler

**I/O Inefficiency Detection:**
- I/O operations count > 100 OR
- I/O time percentage > 30% AND
- Small average bytes per operation (<1KB) OR
- I/O operations inside loops

**Parallelization Opportunity Detection:**
- Parallelization score > 0.6 AND
- Execution time percentage > 5% AND
- Loop iterations > 100 AND
- No loop-carried dependencies

### 3.2 Bottleneck Hypothesis Generation

#### 3.2.1 Initial Hypothesis Formation

Before examining any code, the system generates hypotheses about potential bottlenecks:

**Hypothesis Structure:**

Each hypothesis contains:
- `function_fqn`: The fully qualified name of the suspected function
- `bottleneck_type`: The category of suspected bottleneck
- `confidence_score`: 0-1 score based on evidence strength
- `supporting_evidence`: List of specific metrics supporting the hypothesis
- `expected_impact`: Estimated performance improvement if fixed
- `risk_level`: Assessment of fix complexity and risk

**Hypothesis Ranking:**

Hypotheses are ranked by:
1. Potential impact (execution time × expected improvement)
2. Confidence score (strength of evidence)
3. Risk level (prefer lower risk fixes)
4. Fix complexity (prefer simpler fixes)

**Multi-Bottleneck Detection:**

A single function may have multiple bottleneck hypotheses:
- Algorithm complexity AND caching opportunity
- Memory inefficiency AND parallelization opportunity
These are tracked separately with combined impact estimates

### 3.3 Evidence Pack Assembly

#### 3.3.1 Evidence Pack Structure

For each bottleneck hypothesis, create a comprehensive evidence pack:

**Core Performance Summary:**
- Function FQN and signature
- Execution time (absolute and percentage)
- Call count and call pattern
- Memory usage summary
- Complexity metrics

**Bottleneck-Specific Evidence:**

For Algorithmic Complexity:
- Loop structure analysis
- Complexity growth pattern (O(n), O(n²), etc.)
- Hot line analysis from line profiler
- Data structure operations in loops
- Similar patterns in codebase

For Caching Opportunities:
- Argument repetition patterns
- Most common argument values
- Purity analysis results
- Memory cost of caching
- Cache hit rate estimation

For Memory Inefficiency:
- Allocation patterns and frequencies
- Object lifetime analysis
- Memory growth over time
- Garbage collection impact
- Peak memory usage points

For I/O Inefficiency:
- I/O operation patterns
- Batching opportunities
- Synchronous vs asynchronous potential
- Network/disk latency measurements
- I/O wait time analysis

For Parallelization:
- Loop independence analysis
- Data partition strategy
- Expected speedup (Amdahl's law)
- GIL impact assessment
- Resource contention risks

**Contextual Information:**

- **Execution Context**: Hot paths containing this function
- **Data Flow Context**: Input/output characteristics
- **Call Context**: Main callers and their contribution
- **Code Neighborhood**: Related functions in same module/class

#### 3.3.2 Evidence Enrichment

**Performance Story Generation:**

Create a narrative description of the function's performance:
- "This function is called 1000 times in a loop by `process_all()`"
- "It spends 45% of total runtime, mostly in line 47's list membership test"
- "The same 10 argument combinations account for 90% of calls"
- "Memory grows by 100MB during execution but is freed after"

**Comparative Context:**

Compare the function to others:
- "3x more complex than average function"
- "10x more memory allocation than similar functions"
- "Only CPU-bound function in I/O-heavy module"

**What-If Scenarios:**

Generate hypothetical improvement scenarios:
- "If cached: ~3x speedup, 10MB memory cost"
- "If parallelized: ~4x speedup on 4 cores"
- "If algorithm improved: O(n²)→O(n), ~100x speedup for n=1000"

---

## 4. Phase 3: LLM-Driven Optimization Process

### 4.1 LLM Interaction Strategy

#### 4.1.1 Staged Information Revelation

The LLM interaction follows a deliberate staged approach:

**Stage 1: Hypothesis Review**
- Present performance fingerprints for all functions
- Present execution hot paths
- Present bottleneck hypotheses
- Ask LLM to rank hypotheses and explain reasoning
- No code shown yet

**Stage 2: Targeted Investigation**
- LLM selects specific functions to investigate
- Provide evidence packs for selected functions
- LLM can request specific information via tools
- Still no full code shown

**Stage 3: Code Analysis**
- LLM requests full code for specific functions
- Provide code with performance annotations
- LLM generates optimization proposals

**Stage 4: Fix Generation**
- LLM produces specific code transformations
- System validates proposed changes
- LLM can iterate based on validation results

#### 4.1.2 Tool Interface Specification

The LLM has access to these tools:

**Information Retrieval Tools:**

`get_function_summary(fqn)`:
- Returns performance fingerprint
- Returns signature and docstring
- Returns complexity metrics
- No code included

`get_function_code(fqn)`:
- Returns complete source code
- Returns AST structure summary
- Returns line-level profiling if available

`get_execution_context(fqn)`:
- Returns hot paths containing function
- Returns caller/callee relationships
- Returns data flow information

`get_similar_functions(fqn, similarity_type)`:
- Similarity types: "performance", "structure", "purpose"
- Returns functions with similar characteristics
- Useful for finding repeated patterns

**Analysis Tools:**

`analyze_data_flow(fqn)`:
- Returns input/output characteristics
- Returns data transformation patterns
- Returns dependency information

`estimate_optimization_impact(fqn, optimization_type)`:
- Types: "cache", "parallel", "algorithm", "vectorize"
- Returns estimated speedup
- Returns resource requirements
- Returns implementation complexity

`check_optimization_feasibility(fqn, optimization_type)`:
- Returns whether optimization is applicable
- Returns prerequisites and constraints
- Returns potential risks

**Code Understanding Tools:**

`get_variable_usage(fqn, variable_name)`:
- Returns where variable is defined/used
- Returns data flow for variable
- Returns modification points

`get_loop_analysis(fqn)`:
- Returns detailed loop structure
- Returns iteration patterns
- Returns loop-carried dependencies

`get_dependency_graph(fqn)`:
- Returns functions this depends on
- Returns data dependencies
- Returns external dependencies

### 4.2 Prompt Engineering Strategy

#### 4.2.1 Initial Triage Prompt

The first prompt sets the stage for systematic analysis:

```
You are a performance optimization expert analyzing a Python codebase.

## Performance Profile Summary
[Insert aggregated metrics showing total runtime, memory usage, top functions by time]

## Execution Hot Paths
[Insert top 3-5 hot paths with timing breakdowns]

## Bottleneck Hypotheses
[Insert ranked hypotheses with evidence]

## Your Task
1. Review the performance evidence
2. Identify the most impactful optimization opportunity
3. Explain your reasoning
4. Request specific information needed for optimization

You have access to tools for retrieving additional information. Start with high-level analysis before requesting code.
```

#### 4.2.2 Bottleneck-Specific Prompts

For each bottleneck type, use specialized prompts:

**Algorithmic Complexity Prompt:**
```
## Algorithmic Bottleneck Detected

Function: [FQN]
Evidence:
- Cyclomatic complexity: [value]
- Loop nesting depth: [value]
- Execution time: [percentage]%
- Hot lines: [line numbers]

The function shows signs of algorithmic inefficiency. Based on the metrics:
1. What is the likely complexity class?
2. What data structure changes could help?
3. What algorithmic approaches could reduce complexity?

Use tools to explore the code structure before proposing specific changes.
```

**Caching Opportunity Prompt:**
```
## Caching Opportunity Detected

Function: [FQN]
Evidence:
- Argument repetition rate: [value]
- Common arguments: [top patterns]
- Call count: [value]
- Purity score: [value]

This function appears to be a good caching candidate. Consider:
1. What caching strategy is appropriate?
2. What are the memory implications?
3. How should cache invalidation work?

Analyze the function's purpose and constraints before proposing implementation.
```

#### 4.2.3 Progressive Refinement Strategy

The LLM interaction is iterative:

**Round 1: Hypothesis Validation**
- LLM reviews hypotheses
- Requests clarifying information
- Confirms or refutes hypotheses

**Round 2: Solution Design**
- LLM proposes optimization approach
- System provides feasibility check
- LLM refines approach

**Round 3: Implementation**
- LLM generates specific code changes
- System validates syntax and tests
- LLM fixes any issues

**Round 4: Performance Validation**
- System runs benchmarks
- LLM reviews results
- LLM proposes adjustments if needed

### 4.3 Optimization Plan Generation

#### 4.3.1 Transformation Plan Structure

The LLM produces structured transformation plans:

**Plan Components:**

`reasoning`: Detailed explanation of why this optimization will work

`transformations`: List of specific code changes:
- `type`: The kind of transformation (replace_function, add_decorator, etc.)
- `target`: The FQN of the function to modify
- `details`: Specific parameters for the transformation

`expected_impact`:
- `speedup_estimate`: Expected performance improvement (e.g., "2-3x")
- `confidence`: How certain the estimate is
- `memory_impact`: Expected change in memory usage

`risks`:
- `functional_risks`: Potential for breaking functionality
- `performance_risks`: Scenarios where optimization might not help
- `implementation_complexity`: Difficulty of implementation

`validation_strategy`:
- `required_tests`: What tests must pass
- `performance_criteria`: What benchmarks must show
- `rollback_conditions`: When to revert changes

#### 4.3.2 Transformation Types

**Function-Level Transformations:**

`REPLACE_FUNCTION`: Complete function replacement
- Provide new implementation
- Preserve signature compatibility
- Maintain functional behavior

`ADD_DECORATOR`: Add decorator to function
- Common: @cache, @profile, @parallel
- Include decorator parameters
- Handle decorator ordering

`EXTRACT_FUNCTION`: Extract code into new function
- Identify code to extract
- Create new function
- Update call sites

**Algorithm-Level Transformations:**

`OPTIMIZE_ALGORITHM`: Replace algorithm with better complexity
- Change from O(n²) to O(n log n) or O(n)
- Use better data structures
- Eliminate redundant computations

`ADD_CACHING`: Implement memoization
- Add caching decorator or manual cache
- Define cache key strategy
- Set cache size limits

`PARALLELIZE`: Convert sequential to parallel
- Use multiprocessing or threading
- Define work distribution
- Handle result aggregation

**Data Structure Transformations:**

`CHANGE_DATA_STRUCTURE`: Use more efficient structure
- List to set for membership testing
- List to deque for queue operations
- Dict to defaultdict for initialization

`ADD_INDEX`: Create index for fast lookup
- Build lookup dictionary
- Maintain index consistency
- Balance memory vs speed

### 4.4 Code Transformation Execution

#### 4.4.1 AST-Based Code Modification

Transformations are applied using AST manipulation:

**Transformation Process:**

1. Parse original code into AST
2. Locate target nodes in AST
3. Apply transformation to nodes
4. Convert modified AST back to code
5. Preserve formatting and comments

**Transformation Validation:**

- Syntax validation: Ensure valid Python
- Import validation: Ensure all imports available
- Type validation: Check type consistency if typed
- Style validation: Maintain code style

#### 4.4.2 Testing and Validation

**Test Execution Strategy:**

1. Run existing test suite
2. If no tests exist, generate basic tests:
   - Input/output validation
   - Edge case handling
   - Performance regression tests
3. Compare results before/after optimization

**Performance Benchmarking:**

1. Create micro-benchmark for optimized function
2. Run multiple iterations for statistical validity
3. Measure:
   - Execution time improvement
   - Memory usage change
   - CPU utilization
   - I/O patterns
4. Calculate statistical significance

**Rollback Criteria:**

Automatically rollback if:
- Tests fail
- Performance degrades
- Memory usage exceeds threshold
- Errors occur during execution

---

## 5. Version Management and Decision Making

### 5.1 Version Graph Management

#### 5.1.1 Version Node Structure

Each optimization attempt creates a version node containing:

**Code Snapshot:**
- Complete code for all modified functions
- Diff from parent version
- Transformation plan that created this version

**Performance Metrics:**
- Benchmark results
- Test results  
- Memory profile
- Comparison to parent

**Metadata:**
- Timestamp
- Optimization type
- Target functions
- Success/failure status

#### 5.1.2 Version Tree Navigation

The system maintains a tree of versions:

**Tree Operations:**
- Create child version for each optimization attempt
- Mark successful optimizations as "accepted"
- Mark failed attempts as "rejected"
- Track current active version
- Support rollback to any previous version

**Performance Frontier:**
- Track Pareto-optimal versions
- Balance speed vs memory vs correctness
- Identify best version for different criteria

### 5.2 Optimization Decision Framework

#### 5.2.1 Acceptance Criteria

An optimization is accepted if:

**Correctness Criteria:**
- All existing tests pass
- No new errors introduced
- Functional behavior preserved

**Performance Criteria:**
- Speedup ≥ 10% (configurable threshold)
- Statistical significance (p < 0.05)
- No significant memory regression

**Quality Criteria:**
- Code complexity not significantly increased
- Maintainability preserved
- No introduction of technical debt

#### 5.2.2 Multi-Objective Optimization

Balance multiple objectives:

**Speed vs Memory:**
- Accept memory increase up to threshold for speed gains
- Prefer memory-neutral optimizations when possible

**Complexity vs Performance:**
- Accept complexity increase for significant gains
- Prefer simple optimizations for marginal gains

**Risk vs Reward:**
- Conservative for critical functions
- Aggressive for isolated functions

---

## 6. System Integration and Workflow

### 6.1 Complete Optimization Pipeline

#### 6.1.1 Pipeline Stages

The complete pipeline executes as follows:

**Stage 1: Initialization**
1. Discover project structure
2. Setup profiling environment
3. Run static analysis
4. Execute dynamic profiling
5. Generate performance fingerprints

**Stage 2: Bottleneck Detection**
1. Analyze performance fingerprints
2. Generate bottleneck hypotheses
3. Rank by impact and confidence
4. Assemble evidence packs

**Stage 3: LLM Optimization**
1. Present hypotheses to LLM
2. LLM investigates via tools
3. LLM generates optimization plans
4. Apply transformations

**Stage 4: Validation**
1. Run tests
2. Execute benchmarks
3. Calculate improvements
4. Make accept/reject decision

**Stage 5: Iteration**
1. Update version graph
2. Select next bottleneck
3. Repeat until convergence
4. Generate final report

#### 6.1.2 Convergence Criteria

Stop optimization when:
- No bottlenecks above threshold remain
- Recent optimizations show diminishing returns
- Maximum iteration count reached
- Total speedup target achieved

### 6.2 Output and Reporting

#### 6.2.1 Optimization Report

Generate comprehensive report containing:

**Executive Summary:**
- Total speedup achieved
- Number of optimizations applied
- Memory impact
- Risk assessment

**Detailed Results:**
- Per-function improvements
- Optimization techniques used
- Before/after comparisons
- Statistical validation

**Recommendations:**
- Further optimization opportunities
- Architectural improvements
- Code quality suggestions

#### 6.2.2 Artifacts Produced

The system produces:
- Optimized code
- Performance profiles
- Version history
- Optimization decisions log
- Benchmark results
- Test results

---

## 7. Future Enhancements: Pattern Library with Embeddings

### 7.1 Pattern Library Construction

If implementing pattern-based detection in the future:

#### 7.1.1 Pattern Collection

For each bottleneck type, collect 3-10 examples:

**Example Structure:**
- Before code (with bottleneck)
- After code (optimized)
- Performance metrics before/after
- Explanation of optimization

**Pattern Embedding:**
Embed the "before" examples using:
- Source code
- Performance fingerprint
- AST structure summary
- Complexity metrics

Create vector representation combining:
- Code embedding (from code model)
- Metric embedding (normalized metrics)
- Structural embedding (AST features)

#### 7.1.2 Pattern Matching

When analyzing new code:

**Embedding Process:**
1. Generate embeddings for each function
2. Use same embedding strategy as patterns
3. Ensure consistent normalization

**Similarity Search:**
1. Compare function embeddings to pattern embeddings
2. Use cosine similarity with threshold (e.g., >0.8)
3. Return matching patterns with confidence scores

**Pattern Application:**
1. If match found, provide LLM with:
   - The matched "before" pattern
   - The corresponding "after" pattern
   - The target function code
   - Instructions to apply similar transformation
2. LLM adapts pattern to specific context

### 7.2 Pattern Library Requirements

**Minimum Viable Library:**
- 3-5 examples per bottleneck type minimum
- Examples should be diverse but representative
- Include edge cases and variants
- Document why each optimization works

**Quality Criteria:**
- Examples must be validated (proven optimizations)
- Performance improvements must be significant
- Code must be readable and maintainable
- Patterns must be generalizable

---

## 8. Implementation Checklist

### 8.1 Core Components

Essential components to implement:

1. **Project Scanner**: Discover and catalog Python files
2. **AST Parser**: Extract functions and analyze structure
3. **Static Analyzer**: Calculate complexity metrics
4. **Dynamic Profiler**: Collect runtime performance data
5. **Fingerprint Generator**: Create performance signatures
6. **Hypothesis Generator**: Form bottleneck hypotheses
7. **Evidence Assembler**: Create evidence packs
8. **LLM Interface**: Tool-based interaction system
9. **Code Transformer**: Apply optimizations
10. **Test Runner**: Validate correctness
11. **Benchmark Suite**: Measure improvements
12. **Version Manager**: Track optimization history
13. **Decision Maker**: Accept/reject optimizations
14. **Report Generator**: Produce final outputs

### 8.2 Data Flow

Information flows through the system as:

1. **Raw Code** → Parser → **AST + Chunks**
2. **AST** → Static Analyzer → **Complexity Metrics**
3. **Code Execution** → Profiler → **Runtime Metrics**
4. **Metrics** → Fingerprint Generator → **Performance Fingerprints**
5. **Fingerprints** → Hypothesis Generator → **Bottleneck Hypotheses**
6. **Hypotheses** → Evidence Assembler → **Evidence Packs**
7. **Evidence** → LLM → **Optimization Plans**
8. **Plans** → Transformer → **Modified Code**
9. **Modified Code** → Validator → **Test/Benchmark Results**
10. **Results** → Decision Maker → **Accept/Reject Decision**

### 8.3 Success Criteria

The system is successful when it can:

1. Automatically identify performance bottlenecks
2. Generate correct optimizations
3. Achieve measurable speedups
4. Preserve functional correctness
5. Provide clear explanations
6. Work on diverse Python codebases
7. Handle multiple bottleneck types
8. Produce reproducible results

---

This completes the detailed architectural specification for PEARL. Every component has been specified with enough detail for direct implementation, with clear explanations of what each part does, how it works, and how information flows through the system. The architecture supports targeted, evidence-based optimization with LLM reasoning while maintaining correctness and providing measurable improvements.