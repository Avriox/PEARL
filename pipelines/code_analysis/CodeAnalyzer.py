# CodeAnalyzer.py (renamed from CodeParser.py)
import ast
import hashlib
import io
import json
import logging
import tokenize
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, asdict, field
import astroid
import astor
import networkx as nx
import radon.complexity as radon_cc
import radon.metrics as radon_metrics
import radon.raw as radon_raw
import io
import tokenize
import logging



@dataclass
class StaticFeatures:
    # Core metrics
    cyclomatic_complexity: int = 0
    cognitive_complexity: int = 0
    maintainability_index: float = 0.0
    loc: int = 0
    sloc: int = 0
    num_tokens: int = 0

    # Text/formatting (added)
    blank_lines: int = 0
    comment_lines: int = 0
    comment_density: float = 0.0
    indent_max: float = 0.0
    indent_avg: float = 0.0

    # AST size/shape
    num_nodes: int = 0
    max_ast_depth: int = 0
    attr_chain_max: int = 0

    # Calls
    calls_made: List[str] = field(default_factory=list)
    call_count: int = 0
    num_calls: int = 0
    calls_in_loops: int = 0
    has_recursion: bool = False

    # Control-flow counts
    num_if: int = 0
    num_try: int = 0
    num_except: int = 0
    num_raise: int = 0
    num_assert: int = 0
    num_with: int = 0
    num_ifexp: int = 0

    # Bool/Compare
    num_bool_ops: int = 0
    num_and: int = 0
    num_or: int = 0
    num_not: int = 0
    num_compare: int = 0

    # Loops
    loop_count: int = 0
    num_loops: int = 0
    num_for: int = 0          # added
    num_while: int = 0        # added
    max_loop_depth: int = 0
    max_nesting_depth: int = 0
    has_nested_loops: bool = False
    loops: List[Dict] = field(default_factory=list)
    break_count: int = 0
    continue_count: int = 0

    # Assignments/returns
    num_assign: int = 0
    num_augassign: int = 0
    num_annassign: int = 0
    num_return: int = 0
    num_yield: int = 0

    # Imports/scope
    num_import: int = 0
    num_importfrom: int = 0
    num_global: int = 0
    num_nonlocal: int = 0

    # Literals
    num_list_literals: int = 0
    num_dict_literals: int = 0
    num_set_literals: int = 0
    num_tuple_literals: int = 0
    max_list_literal_len: int = 0
    max_dict_literal_len: int = 0
    max_set_literal_len: int = 0
    max_tuple_literal_len: int = 0
    max_string_length: int = 0
    num_long_strings: int = 0

    # Functions/classes
    num_lambda: int = 0
    num_classdef: int = 0
    num_funcdef: int = 0
    avg_params_per_func: float = 0.0
    max_params_per_func: int = 0

    # Data structure ops
    list_operations: int = 0
    dict_operations: int = 0
    set_operations: int = 0
    tuple_operations: int = 0
    comprehensions: int = 0
    subscript_in_loops: int = 0

    # Comprehension breakdown
    num_comprehensions: int = 0
    comprehension_loops: int = 0
    comprehension_ifs: int = 0

    # External call families and IO/regex/sort
    numpy_calls: int = 0
    pandas_calls: int = 0
    regex_operations: int = 0
    regex_calls: int = 0
    db_operations: int = 0
    http_operations: int = 0
    sort_calls: int = 0
    open_calls: int = 0
    io_calls: int = 0
    append_calls_in_loop: int = 0

    # Concurrency
    uses_threading: bool = False
    uses_multiprocessing: bool = False
    uses_asyncio: bool = False
    concurrency_primitives: List[str] = field(default_factory=list)

    # External calls detail
    external_calls: Dict[str, int] = field(default_factory=dict)


@dataclass
class FunctionChunk:
    chunk_type: str = "function"
    fqn: str = ""
    project_id: str = ""
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    ast_hash: str = ""
    source_code: str = ""
    version: int = 0
    signature: str = ""
    decorators: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    called_functions: List[str] = field(default_factory=list)
    parameters: List[str] = field(default_factory=list)
    return_annotation: Optional[str] = None
    is_async: bool = False
    is_method: bool = False
    is_staticmethod: bool = False
    is_classmethod: bool = False
    is_property: bool = False
    class_name: Optional[str] = None
    module_name: str = ""
    static_features: Optional[StaticFeatures] = None
    is_slow: bool = False


@dataclass
class ClassChunk:
    chunk_type: str = "class"
    fqn: str = ""
    project_id: str = ""
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    ast_hash: str = ""
    source_code: str = ""
    version: int = 0
    decorators: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    base_classes: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)
    class_attributes: List[str] = field(default_factory=list)
    module_name: str = ""


@dataclass
class ModuleChunk:
    chunk_type: str = "module"
    fqn: str = ""
    project_id: str = ""
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    ast_hash: str = ""
    source_code: str = ""
    version: int = 0
    docstring: Optional[str] = None
    imports: List[Dict] = field(default_factory=list)
    from_imports: List[Dict] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    global_variables: List[Dict] = field(default_factory=list)


import ast
from pathlib import Path
from collections import defaultdict


class FQNResolver:
    def __init__(self, db, project_id: str, project_root: Path):
        self.db = db
        self.project_id = project_id
        self.root = Path(project_root).resolve()
        self.by_file = defaultdict(list)
        self._ast_cache = {}

        rows = db.execute_sql(
            f"""
    WITH latest AS (
        SELECT fqn, MAX(version) AS v
        FROM functions
        WHERE project_id = '{project_id}'
        GROUP BY fqn
    )
    SELECT
        f.fqn,
        f.module_name,
        f.function_name,
        f.class_name,
        f.file_path,
        f.start_line,
        f.end_line
    FROM functions AS f
    JOIN latest AS l
      ON f.fqn = l.fqn AND f.version = l.v
    WHERE f.project_id = '{project_id}'
    """
        )
        for r in rows:
            rel = str(Path(r["file_path"]).as_posix())
            self.by_file[rel].append(r)

    def rel_to_project(self, path: str) -> str:
        p = Path(path)
        try:
            return str(p.resolve().relative_to(self.root).as_posix())
        except Exception:
            return str(Path(path).as_posix())

    def module_from_rel(self, rel: str) -> str:
        return ".".join(Path(rel).with_suffix("").parts)

    def guess_rel_from_module(self, module: str) -> str:
        return (module or "").replace(".", "/") + ".py"

    def resolve(
        self, file_path: str, lineno: int, fallback_module: str, funcname: str
    ) -> str:
        if not file_path:
            # no file — best effort
            return f"{fallback_module}.{funcname}".strip(".")

        rel_proj = self.rel_to_project(file_path)
        candidates = []
        # Try: exact project-relative match
        if rel_proj in self.by_file:
            candidates = self.by_file[rel_proj]
        else:
            # Try: module-based guess (e.g., for site-packages)
            rel_guess = self.guess_rel_from_module(fallback_module)
            candidates = self.by_file.get(rel_guess, [])

            # Try: suffix match (last N components) if still missing
            if not candidates:
                suffix = "/".join(Path(rel_proj).parts[-3:])  # last 3 components
                for k, rows in self.by_file.items():
                    if k.endswith(suffix):
                        candidates = rows
                        break

        for c in candidates:
            if c["start_line"] <= lineno <= c["end_line"]:
                return c["fqn"]

        # AST fallback: parse the file and determine Class.func
        try:
            resolved = self._resolve_by_ast(
                file_path, lineno, fallback_module, funcname
            )
            if resolved:
                return resolved
        except Exception:
            pass

        # Ultimate fallback
        module = fallback_module or self.module_from_rel(rel_proj)
        return f"{module}.{funcname}".strip(".")

    def _resolve_by_ast(
        self, file_path: str, lineno: int, fallback_module: str, funcname: str
    ) -> str | None:
        p = Path(file_path)
        if p not in self._ast_cache:
            try:
                src = p.read_text(encoding="utf-8")
                self._ast_cache[p] = (src, ast.parse(src))
            except Exception:
                return None
        src, tree = self._ast_cache[p]

        # Walk to find the smallest FunctionDef/AsyncFunctionDef containing lineno
        best = None  # (depth, class_name, func_name, start, end)
        class_stack = []

        class NodeVisitor(ast.NodeVisitor):
            def generic_visit(self, node):
                nonlocal best
                if isinstance(node, ast.ClassDef):
                    class_stack.append(node.name)
                    super().generic_visit(node)
                    class_stack.pop()
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    start = node.lineno
                    end = getattr(node, "end_lineno", node.lineno)
                    if start <= lineno <= end:
                        depth = len(class_stack)
                        cand = (
                            depth,
                            class_stack[-1] if class_stack else None,
                            node.name,
                            start,
                            end,
                        )
                        if best is None or cand[0] >= best[0]:
                            best = cand
                    super().generic_visit(node)
                else:
                    super().generic_visit(node)

        NodeVisitor().visit(tree)

        module = fallback_module or self.module_from_rel(self.rel_to_project(file_path))
        if best:
            _, cls, fn, *_ = best
            if cls:
                return f"{module}.{cls}.{fn}"
            return f"{module}.{fn}"
        return None


def _apply_cprofile_to_metrics(self, func_metrics_from_pyi, cp_payload):
    # Build metrics keyed by (file, line, funcname) to avoid collapsing same-named methods
    metrics = {}

    # Example record fields – adjust to your actual payload
    # cp_payload["functions"] -> list of dicts with filename, lineno, funcname, ncalls, tottime_ms, cumtime_ms
    for rec in cp_payload.get("functions", []):
        filename = rec["filename"]
        lineno = int(rec["lineno"])
        funcname = rec["funcname"]
        tottime = float(rec.get("tottime_ms", 0.0))
        cumtime = float(rec.get("cumtime_ms", 0.0))
        ncalls = int(rec.get("ncalls", 0))

        key = (filename, lineno, funcname)

        if key not in metrics:
            fm = FunctionMetrics(
                fqn="",  # resolved later
                inclusive_time_ms=cumtime,
                exclusive_time_ms=tottime,
                call_count=ncalls,
                avg_time_ms=0.0,
                fraction_of_total=0.0,
                file_path=filename,
                module_name=self._module_from_path(filename),  # best-effort
                function_name=funcname,
                first_lineno=lineno,
            )
            metrics[key] = fm
        else:
            fm = metrics[key]
            fm.inclusive_time_ms += cumtime
            fm.exclusive_time_ms += tottime
            fm.call_count += ncalls

    # Return as a dict keyed by a temp string so caller stays unchanged
    out = {}
    for (filename, lineno, funcname), fm in metrics.items():
        temp_key = f"{fm.module_name}.{funcname}@L{lineno}"
        fm.fqn = temp_key
        out[temp_key] = fm
    return out


def _module_from_path(self, path: str) -> str:
    from pathlib import Path

    try:
        rel = Path(path).resolve().relative_to(self.project.directory.resolve())
        return ".".join(Path(rel).with_suffix("").parts)
    except Exception:
        return ".".join(Path(path).with_suffix("").parts)


class CodeAnalyzer:
    """Unified code analysis: parsing, chunking, and static analysis"""

    def __init__(self, project_id: str, project_root: Path):
        self.project_id = project_id
        self.project_root = Path(project_root)
        self.chunks: List[Any] = []
        self.call_graph = nx.DiGraph()

    def analyze_project(self) -> Tuple[List[Any], nx.DiGraph]:
        """Analyze all Python files in the project"""
        logging.info(f"Analyzing project {self.project_id}")

        python_files = list(self.project_root.rglob("*.py"))
        python_files = [
            f
            for f in python_files
            if not any(skip in str(f) for skip in [".venv", "__pycache__", "run_logs"])
        ]

        logging.info(f"Found {len(python_files)} Python files")

        for py_file in python_files:
            try:
                self.analyze_file(py_file)
            except Exception as e:
                logging.error(f"Failed to analyze {py_file}: {e}")

        return self.chunks, self.call_graph

    def analyze_file(self, file_path: Path) -> List[Any]:
        """Analyze a single file - parse once, extract everything"""
        logging.debug(f"Analyzing file: {file_path}")

        # Read source code
        with open(file_path, "r", encoding="utf-8") as f:
            source_code = f.read()

        # Parse AST once
        try:
            tree = ast.parse(source_code, filename=str(file_path))
        except SyntaxError as e:
            logging.error(f"Syntax error in {file_path}: {e}")
            return []

        # Get module info
        module_fqn = self._get_module_fqn(file_path)
        relative_path = file_path.relative_to(self.project_root)

        # Create module chunk
        module_chunk = self._create_module_chunk(
            tree, source_code, relative_path, module_fqn
        )
        self.chunks.append(module_chunk)

        # Process all nodes in the module
        file_chunks = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_chunk = self._process_function(
                    node, source_code, relative_path, module_fqn, None, tree
                )
                self.chunks.append(func_chunk)
                file_chunks.append(func_chunk)

            elif isinstance(node, ast.ClassDef):
                class_chunk, method_chunks = self._process_class(
                    node, source_code, relative_path, module_fqn, tree
                )
                self.chunks.append(class_chunk)
                self.chunks.extend(method_chunks)
                file_chunks.append(class_chunk)
                file_chunks.extend(method_chunks)

        # Build call graph edges
        for chunk in file_chunks:
            if isinstance(chunk, FunctionChunk) and chunk.static_features:
                self._add_to_call_graph(chunk.fqn, chunk.static_features.calls_made)

        return file_chunks

    def _process_function(
            self,
            node: ast.AST,
            source: str,
            file_path: Path,
            module_fqn: str,
            class_name: Optional[str],
            module_tree: ast.AST,
    ) -> FunctionChunk:
        func_name = node.name
        # Fully resolved FQN: module.Class.func or module.func
        fqn = (
            f"{module_fqn}.{class_name}.{func_name}"
            if class_name
            else f"{module_fqn}.{func_name}"
        )
        is_method = class_name is not None

        decorators = [astor.to_source(d).strip() for d in node.decorator_list]
        docstring = ast.get_docstring(node)
        parameters = [arg.arg for arg in node.args.args]

        return_annotation = None
        if node.returns:
            return_annotation = astor.to_source(node.returns).strip()

        signature = f"{func_name}({', '.join(parameters)})"
        if return_annotation:
            signature += f" -> {return_annotation}"

        source_lines = source.split("\n")
        func_source = "\n".join(source_lines[node.lineno - 1 : node.end_lineno])

        # Detect inline “bottleneck” label just above the function
        is_slow = self._detect_bottleneck_marker_before(source, node.lineno)

        # Pass class_name so we normalize self/cls/super calls
        static_features = self._analyze_function_ast(
            node, func_source, module_fqn, class_name
        )

        is_staticmethod = any("staticmethod" in d for d in decorators)
        is_classmethod = any("classmethod" in d for d in decorators)
        is_property = any("property" in d for d in decorators)

        return FunctionChunk(
            chunk_type="function",
            fqn=fqn,
            project_id=self.project_id,
            file_path=str(file_path),
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            ast_hash=self._compute_ast_hash(node),
            source_code=func_source,
            signature=signature,
            decorators=decorators,
            docstring=docstring,
            called_functions=static_features.calls_made,
            parameters=parameters,
            return_annotation=return_annotation,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_method=is_method,
            is_staticmethod=is_staticmethod,
            is_classmethod=is_classmethod,
            is_property=is_property,
            class_name=class_name,
            module_name=module_fqn,
            static_features=static_features,
            is_slow=is_slow,  # <— here
        )

    def _process_class(
        self,
        node: ast.ClassDef,
        source: str,
        file_path: Path,
        module_fqn: str,
        module_tree: ast.AST,
    ) -> Tuple[ClassChunk, List[FunctionChunk]]:
        """Process class and its methods"""

        class_name = node.name
        fqn = f"{module_fqn}.{class_name}"

        decorators = [astor.to_source(d).strip() for d in node.decorator_list]
        base_classes = [astor.to_source(b).strip() for b in node.bases]
        docstring = ast.get_docstring(node)

        methods = []
        method_chunks = []
        class_attributes = []

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_chunk = self._process_function(
                    item, source, file_path, module_fqn, class_name, module_tree
                )
                methods.append(method_chunk.fqn)  # fully resolved now
                method_chunks.append(method_chunk)
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        class_attributes.append(target.id)

        source_lines = source.split("\n")
        class_source = "\n".join(source_lines[node.lineno - 1 : node.end_lineno])

        class_chunk = ClassChunk(
            fqn=fqn,
            project_id=self.project_id,
            file_path=str(file_path),
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            ast_hash=self._compute_ast_hash(node),
            source_code=class_source,
            decorators=decorators,
            docstring=docstring,
            base_classes=base_classes,
            methods=methods,
            class_attributes=class_attributes,
            module_name=module_fqn,
        )

        return class_chunk, method_chunks

    def _analyze_function_ast(
            self,
            node: ast.AST,
            source_code: str,
            module_fqn: str,
            class_name: Optional[str] = None,
    ) -> StaticFeatures:
        """Analyze a function's AST node for static features"""
        import io
        import tokenize
        import logging

        features = StaticFeatures()

        # Complexity, MI, raw metrics (via radon)
        try:
            cc_results = radon_cc.cc_visit(source_code)
            if cc_results:
                features.cyclomatic_complexity = cc_results[0].complexity
            mi = radon_metrics.mi_visit(source_code, multi=False)
            if mi:
                features.maintainability_index = mi
            raw = radon_raw.analyze(source_code)
            features.loc = raw.loc
            features.sloc = raw.sloc
        except Exception:
            pass

        # Text features to match embedding project's _text_loc_features
        try:
            lines = source_code.splitlines()
            loc_text = len(lines)
            blank = sum(1 for l in lines if not l.strip())
            comments = sum(1 for l in lines if l.lstrip().startswith("#"))
            indents = []
            for l in lines:
                if l.strip():
                    nspace = len(l) - len(l.lstrip(" "))
                    indents.append(int(nspace // 4))
            indent_max = max(indents) if indents else 0
            indent_avg = (sum(indents) / len(indents)) if indents else 0.0

            features.blank_lines = blank
            features.comment_lines = comments
            features.comment_density = (comments / loc_text) if loc_text > 0 else 0.0
            features.indent_max = float(indent_max)
            features.indent_avg = float(indent_avg)
        except Exception:
            # leave defaults
            pass

        # Token count
        try:
            toks = list(tokenize.generate_tokens(io.StringIO(source_code).readline))
            features.num_tokens = max(0, len(toks))
        except Exception:
            features.num_tokens = 0

        # Loops
        loop_info = self._analyze_loops(node)
        features.loop_count = loop_info["count"]
        features.num_loops = loop_info["count"]
        features.max_nesting_depth = loop_info["max_depth"]
        features.has_nested_loops = loop_info["has_nested"]
        features.loops = loop_info["loops"]

        # Data structures
        data_usage = self._analyze_data_structures(node, loop_info["loop_nodes"])
        features.list_operations = data_usage["list"]
        features.dict_operations = data_usage["dict"]
        features.set_operations = data_usage["set"]
        features.tuple_operations = data_usage["tuple"]
        features.comprehensions = data_usage["comprehensions"]
        features.subscript_in_loops = data_usage["subscript_in_loops"]

        # External calls
        external = self._detect_external_calls(node)
        features.numpy_calls = external["numpy"]
        features.pandas_calls = external["pandas"]
        features.regex_operations = external["regex"]
        features.db_operations = external["database"]
        features.http_operations = external["http"]
        features.external_calls = external["all_external"]

        # Concurrency
        concurrency = self._detect_concurrency(node, source_code)
        features.uses_threading = concurrency["threading"]
        features.uses_multiprocessing = concurrency["multiprocessing"]
        features.uses_asyncio = concurrency["asyncio"]
        features.concurrency_primitives = concurrency["primitives"]

        # Calls made
        func_name = getattr(node, "name", "")
        fqn = f"{module_fqn}.{func_name}" if class_name is None else f"{module_fqn}.{class_name}.{func_name}"
        calls = self._extract_calls(node, module_fqn, class_name)
        features.calls_made = calls["direct_calls"]
        features.call_count = calls["count"]
        features.has_recursion = any(c == fqn for c in features.calls_made)

        # Detailed visitor (aligned with embedding project)
        def _attr_chain_len(n: ast.AST) -> int:
            l, cur = 0, n
            while isinstance(cur, ast.Attribute):
                l += 1
                cur = cur.value
            if isinstance(cur, ast.Name):
                l += 1
            return l

        class V(ast.NodeVisitor):
            def __init__(self):
                # shape
                self.num_nodes = 0
                self.depth = 0
                self.max_depth = 0
                self.attr_chain_max = 0
                # loops
                self.loop_depth = 0
                self.max_loop_depth = 0
                # calls
                self.n_calls = 0
                self.calls_in_loops = 0
                self.call_names = {}
                # control flow
                self.n_if = 0; self.n_try = 0; self.n_except = 0
                self.n_raise = 0; self.n_assert = 0; self.n_with = 0
                self.n_ifexp = 0
                # bool/compare
                self.n_bool_ops = 0; self.n_and = 0; self.n_or = 0; self.n_not = 0
                self.n_compare = 0
                # loop counters
                self.n_for = 0; self.n_while = 0
                self.n_break = 0; self.n_continue = 0
                # assignments/returns
                self.n_assign = 0; self.n_augassign = 0; self.n_annassign = 0
                self.n_return = 0; self.n_yield = 0; self.n_yield_from = 0
                # imports/scope
                self.n_import = 0; self.n_importfrom = 0
                self.n_global = 0; self.n_nonlocal = 0
                # literals
                self.n_list_literals = 0; self.n_dict_literals = 0
                self.n_set_literals = 0; self.n_tuple_literals = 0
                self.max_list_literal_len = 0; self.max_dict_literal_len = 0
                self.max_set_literal_len = 0; self.max_tuple_literal_len = 0
                self.max_string_length = 0; self.num_long_strings = 0
                # defs
                self.n_lambda = 0; self.n_classdef = 0; self.n_funcdef = 0
                self.total_params = 0; self.max_params = 0
                # comprehensions
                self.n_comprehensions = 0
                self.comprehension_loops = 0
                self.comprehension_ifs = 0
                # patterns
                self.n_regex_calls = 0; self.n_sort_calls = 0
                self.n_open_calls = 0; self.n_io_calls = 0
                self.append_calls_in_loop = 0

            def generic_visit(self, n):
                self.num_nodes += 1
                self.depth += 1
                self.max_depth = max(self.max_depth, self.depth)
                if isinstance(n, ast.Attribute):
                    self.attr_chain_max = max(self.attr_chain_max, _attr_chain_len(n))
                super().generic_visit(n)
                self.depth -= 1

            def visit_If(self, n): self.n_if += 1; self.generic_visit(n)
            def visit_IfExp(self, n): self.n_ifexp += 1; self.generic_visit(n)

            def visit_For(self, n):
                self.n_for += 1
                self.loop_depth += 1
                self.max_loop_depth = max(self.max_loop_depth, self.loop_depth)
                self.generic_visit(n)
                self.loop_depth -= 1

            def visit_While(self, n):
                self.n_while += 1
                self.loop_depth += 1
                self.max_loop_depth = max(self.max_loop_depth, self.loop_depth)
                self.generic_visit(n)
                self.loop_depth -= 1

            def visit_Break(self, n): self.n_break += 1
            def visit_Continue(self, n): self.n_continue += 1
            def visit_Try(self, n): self.n_try += 1; self.generic_visit(n)
            def visit_ExceptHandler(self, n): self.n_except += 1; self.generic_visit(n)
            def visit_Raise(self, n): self.n_raise += 1; self.generic_visit(n)
            def visit_Assert(self, n): self.n_assert += 1; self.generic_visit(n)
            def visit_With(self, n): self.n_with += 1; self.generic_visit(n)
            def visit_UnaryOp(self, n):
                if isinstance(n.op, ast.Not): self.n_not += 1
                self.generic_visit(n)
            def visit_BoolOp(self, n):
                self.n_bool_ops += 1
                links = max(0, len(getattr(n, "values", [])) - 1)
                if isinstance(n.op, ast.And): self.n_and += links if links > 0 else 1
                elif isinstance(n.op, ast.Or): self.n_or += links if links > 0 else 1
                self.generic_visit(n)
            def visit_Compare(self, n): self.n_compare += max(1, len(getattr(n, "ops", []))); self.generic_visit(n)

            def _call_name(self, f) -> str:
                try:
                    if isinstance(f, ast.Name): return f.id
                    parts = []; cur = f
                    while isinstance(cur, ast.Attribute):
                        parts.append(cur.attr); cur = cur.value
                    if isinstance(cur, ast.Name):
                        parts.append(cur.id); return ".".join(reversed(parts))
                    return "_unknown"
                except Exception:
                    return "_unknown"

            def visit_Call(self, n):
                self.n_calls += 1
                if self.loop_depth > 0: self.calls_in_loops += 1
                nm = self._call_name(n.func)
                self.call_names[nm] = self.call_names.get(nm, 0) + 1
                if nm == "open" or nm.endswith(".open"): self.n_open_calls += 1; self.n_io_calls += 1
                if nm == "sorted" or nm.endswith(".sort"):
                    self.n_sort_calls += 1
                    if self.loop_depth > 0: self.calls_in_loops += 1
                if nm == "print": self.n_io_calls += 1
                if isinstance(n.func, ast.Attribute) and n.func.attr == "append" and self.loop_depth > 0:
                    self.append_calls_in_loop += 1
                if nm.startswith("re.") and any(x in nm for x in ["compile","match","search","findall","sub"]):
                    self.n_regex_calls += 1
                self.generic_visit(n)

            def visit_ListComp(self, n):
                self.n_comprehensions += 1
                self.comprehension_loops += len(n.generators)
                for gen in n.generators:
                    self.comprehension_ifs += len(getattr(gen, "ifs", []))
                self.generic_visit(n)

            def visit_SetComp(self, n):
                self.n_comprehensions += 1
                self.comprehension_loops += len(n.generators)
                for gen in n.generators:
                    self.comprehension_ifs += len(getattr(gen, "ifs", []))
                self.generic_visit(n)

            def visit_DictComp(self, n):
                self.n_comprehensions += 1
                self.comprehension_loops += len(n.generators)
                for gen in n.generators:
                    self.comprehension_ifs += len(getattr(gen, "ifs", []))
                self.generic_visit(n)

            def visit_GeneratorExp(self, n):
                self.n_comprehensions += 1
                self.comprehension_loops += len(n.generators)
                for gen in n.generators:
                    self.comprehension_ifs += len(getattr(gen, "ifs", []))
                self.generic_visit(n)

            def visit_Assign(self, n): self.n_assign += 1; self.generic_visit(n)
            def visit_AugAssign(self, n): self.n_augassign += 1; self.generic_visit(n)
            def visit_AnnAssign(self, n): self.n_annassign += 1; self.generic_visit(n)
            def visit_Return(self, n): self.n_return += 1; self.generic_visit(n)
            def visit_Yield(self, n): self.n_yield += 1; self.generic_visit(n)
            def visit_YieldFrom(self, n): self.n_yield_from += 1; self.generic_visit(n)
            def visit_Import(self, n): self.n_import += 1; self.generic_visit(n)
            def visit_ImportFrom(self, n): self.n_importfrom += 1; self.generic_visit(n)
            def visit_Global(self, n): self.n_global += 1; self.generic_visit(n)
            def visit_Nonlocal(self, n): self.n_nonlocal += 1; self.generic_visit(n)
            def visit_List(self, n):
                self.n_list_literals += 1
                self.max_list_literal_len = max(self.max_list_literal_len, len(getattr(n, "elts", []) or []))
                self.generic_visit(n)
            def visit_Dict(self, n):
                self.n_dict_literals += 1
                self.max_dict_literal_len = max(self.max_dict_literal_len, len(getattr(n, "keys", []) or []))
                self.generic_visit(n)
            def visit_Set(self, n):
                self.n_set_literals += 1
                self.max_set_literal_len = max(self.max_set_literal_len, len(getattr(n, "elts", []) or []))
                self.generic_visit(n)
            def visit_Tuple(self, n):
                self.n_tuple_literals += 1
                self.max_tuple_literal_len = max(self.max_tuple_literal_len, len(getattr(n, "elts", []) or []))
                self.generic_visit(n)
            def visit_Constant(self, n):
                if isinstance(n.value, str):
                    ln = len(n.value)
                    self.max_string_length = max(self.max_string_length, ln)
                    if ln >= 80: self.num_long_strings += 1
                self.generic_visit(n)
            def _count_params(self, args: ast.arguments) -> int:
                total = 0
                total += len(getattr(args, "posonlyargs", []))
                total += len(getattr(args, "args", []))
                total += len(getattr(args, "kwonlyargs", []))
                if getattr(args, "vararg", None) is not None: total += 1
                if getattr(args, "kwarg", None) is not None: total += 1
                return total
            def visit_FunctionDef(self, n):
                self.n_funcdef += 1
                params = self._count_params(n.args)
                self.total_params += params
                self.max_params = max(self.max_params, params)
                self.generic_visit(n)
            def visit_AsyncFunctionDef(self, n):
                self.n_funcdef += 1
                params = self._count_params(n.args)
                self.total_params += params
                self.max_params = max(self.max_params, params)
                self.generic_visit(n)
            def visit_ClassDef(self, n): self.n_classdef += 1; self.generic_visit(n)

        v = V()
        # Prefer visiting a standalone parse of the function source; fall back to the original node
        try:
            local_tree = ast.parse(source_code)
            v.visit(local_tree)
        except Exception:
            try:
                v.visit(node)
            except Exception:
                logging.exception("Static visitor failed; leaving visitor-derived counts at defaults")

        # Fill features from visitor
        features.num_nodes = v.num_nodes
        features.max_ast_depth = v.max_depth
        features.attr_chain_max = v.attr_chain_max

        features.num_calls = v.n_calls or features.call_count
        features.calls_in_loops = v.calls_in_loops

        features.num_if = v.n_if
        features.num_try = v.n_try
        features.num_except = v.n_except
        features.num_raise = v.n_raise
        features.num_assert = v.n_assert
        features.num_with = v.n_with
        features.num_ifexp = v.n_ifexp

        features.num_bool_ops = v.n_bool_ops
        features.num_and = v.n_and
        features.num_or = v.n_or
        features.num_not = v.n_not
        features.num_compare = v.n_compare

        features.num_for = v.n_for           # ensure present
        features.num_while = v.n_while       # ensure present
        features.max_loop_depth = max(v.max_loop_depth, loop_info["max_depth"])
        features.break_count = v.n_break
        features.continue_count = v.n_continue

        features.num_assign = v.n_assign
        features.num_augassign = v.n_augassign
        features.num_annassign = v.n_annassign
        features.num_return = v.n_return
        features.num_yield = v.n_yield + v.n_yield_from

        features.num_import = v.n_import
        features.num_importfrom = v.n_importfrom
        features.num_global = v.n_global
        features.num_nonlocal = v.n_nonlocal

        features.num_list_literals = v.n_list_literals
        features.num_dict_literals = v.n_dict_literals
        features.num_set_literals = v.n_set_literals
        features.num_tuple_literals = v.n_tuple_literals
        features.max_list_literal_len = v.max_list_literal_len
        features.max_dict_literal_len = v.max_dict_literal_len
        features.max_set_literal_len = v.max_set_literal_len
        features.max_tuple_literal_len = v.max_tuple_literal_len
        features.max_string_length = v.max_string_length
        features.num_long_strings = v.num_long_strings

        features.num_lambda = v.n_lambda
        features.num_classdef = v.n_classdef
        features.num_funcdef = v.n_funcdef
        features.avg_params_per_func = (v.total_params / v.n_funcdef) if v.n_funcdef > 0 else 0.0
        features.max_params_per_func = v.max_params

        features.num_comprehensions = v.n_comprehensions
        features.comprehension_loops = v.comprehension_loops
        features.comprehension_ifs = v.comprehension_ifs

        features.regex_calls = v.n_regex_calls
        features.sort_calls = v.n_sort_calls
        features.open_calls = v.n_open_calls
        features.io_calls = v.n_io_calls
        features.append_calls_in_loop = v.append_calls_in_loop

        # Consistency
        features.has_nested_loops = features.max_nesting_depth > 1 or features.max_loop_depth > 1

        return features

    def _analyze_loops(self, node: ast.AST) -> Dict:
        """Analyze loops in the function"""
        loops = []
        loop_nodes = []
        max_depth = 0

        def analyze_node(n, depth=0):
            nonlocal max_depth
            for child in ast.iter_child_nodes(n):
                if isinstance(child, (ast.For, ast.While)):
                    current_depth = depth + 1
                    max_depth = max(max_depth, current_depth)

                    loop_type = "for" if isinstance(child, ast.For) else "while"
                    pattern = None

                    if isinstance(child, ast.For) and isinstance(child.iter, ast.Call):
                        if isinstance(child.iter.func, ast.Name):
                            pattern = child.iter.func.id

                    loops.append(
                        {
                            "type": loop_type,
                            "depth": current_depth,
                            "line": child.lineno,
                            "pattern": pattern,
                        }
                    )

                    loop_nodes.append(child)
                    analyze_node(child, current_depth)
                else:
                    analyze_node(child, depth)

        analyze_node(node)

        return {
            "loops": loops,
            "loop_nodes": loop_nodes,
            "count": len(loops),
            "max_depth": max_depth,
            "has_nested": max_depth > 1,
        }

    def _analyze_data_structures(self, node: ast.AST, loop_nodes: List) -> Dict:
        """Count data structure operations"""
        stats = {
            "list": 0,
            "dict": 0,
            "set": 0,
            "tuple": 0,
            "comprehensions": 0,
            "subscript_in_loops": 0,
        }

        def in_loop(n):
            for loop in loop_nodes:
                if n in ast.walk(loop):
                    return True
            return False

        for n in ast.walk(node):
            if isinstance(n, ast.List):
                stats["list"] += 1
            elif isinstance(n, ast.Dict):
                stats["dict"] += 1
            elif isinstance(n, ast.Set):
                stats["set"] += 1
            elif isinstance(n, ast.Tuple):
                stats["tuple"] += 1
            elif isinstance(n, (ast.ListComp, ast.DictComp, ast.SetComp)):
                stats["comprehensions"] += 1
            elif isinstance(n, ast.Subscript) and in_loop(n):
                stats["subscript_in_loops"] += 1

        return stats

    def _detect_external_calls(self, node: ast.AST) -> Dict:
        """Detect external library calls"""
        stats = {
            "numpy": 0,
            "pandas": 0,
            "regex": 0,
            "database": 0,
            "http": 0,
            "all_external": {},
        }

        external_modules = {
            "numpy": ["np", "numpy"],
            "pandas": ["pd", "pandas"],
            "regex": ["re"],
            "database": ["sqlite3", "psycopg2", "pymongo"],
            "http": ["requests", "urllib", "httpx"],
        }

        for n in ast.walk(node):
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
                name = n.value.id
                for category, modules in external_modules.items():
                    if name in modules:
                        stats[category] += 1
                        key = f"{name}.{n.attr}"
                        stats["all_external"][key] = (
                            stats["all_external"].get(key, 0) + 1
                        )

        return stats

    def _detect_concurrency(self, node: ast.AST, source_code: str) -> Dict:
        """Detect concurrency patterns"""
        result = {
            "threading": False,
            "multiprocessing": False,
            "asyncio": False,
            "primitives": [],
        }

        if "async def" in source_code:
            result["asyncio"] = True
            result["primitives"].append("async_function")

        concurrency_names = {
            "Thread": "threading",
            "Process": "multiprocessing",
            "Pool": "multiprocessing",
            "Queue": "queue",
            "Lock": "threading",
            "gather": "asyncio",
        }

        for n in ast.walk(node):
            if isinstance(n, ast.Name):
                for pattern, module in concurrency_names.items():
                    if pattern in n.id:
                        result[module.split(".")[0]] = True
                        result["primitives"].append(f"{pattern}({module})")

        result["primitives"] = list(set(result["primitives"]))
        return result

    def _extract_calls(
        self, node: ast.AST, module_fqn: str, class_name: Optional[str] = None
    ) -> Dict:
        """Extract function calls; normalize to fully resolved FQNs when possible."""
        direct_calls = []

        def is_super_call(x: ast.AST) -> bool:
            return (
                isinstance(x, ast.Call)
                and isinstance(x.func, ast.Name)
                and x.func.id == "super"
            )

        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                f = n.func
                try:
                    if isinstance(f, ast.Name):
                        # Unqualified call: assume module-level function
                        direct_calls.append(f"{module_fqn}.{f.id}")
                    elif isinstance(f, ast.Attribute):
                        base = f.value
                        if isinstance(base, ast.Name) and base.id in ("self", "cls"):
                            if class_name:
                                direct_calls.append(
                                    f"{module_fqn}.{class_name}.{f.attr}"
                                )
                            else:
                                direct_calls.append(f"{module_fqn}.{f.attr}")
                        elif isinstance(base, ast.Call) and is_super_call(base):
                            if class_name:
                                direct_calls.append(
                                    f"{module_fqn}.{class_name}.{f.attr}"
                                )
                            else:
                                direct_calls.append(f"{module_fqn}.{f.attr}")
                        elif isinstance(base, ast.Name):
                            # External/module alias like np.sum or requests.get
                            direct_calls.append(f"{base.id}.{f.attr}")
                        else:
                            # Fallback textual representation
                            direct_calls.append(astor.to_source(f).strip())
                except Exception:
                    pass

        return {"direct_calls": sorted(set(direct_calls)), "count": len(direct_calls)}

    def _estimate_cognitive_complexity(self, node: ast.AST) -> int:
        """Estimate cognitive complexity"""
        complexity = 0

        for n in ast.walk(node):
            if isinstance(n, (ast.If, ast.While, ast.For)):
                complexity += 1
            elif isinstance(n, ast.BoolOp):
                complexity += len(n.values) - 1
            elif isinstance(n, (ast.Break, ast.Continue)):
                complexity += 1

        return complexity

    def _create_module_chunk(
        self, tree: ast.Module, source: str, file_path: Path, module_fqn: str
    ) -> ModuleChunk:
        """Create module chunk"""
        docstring = ast.get_docstring(tree)

        imports = []
        from_imports = []
        functions = []
        classes = []
        global_vars = []

        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(
                        {
                            "module": alias.name,
                            "alias": alias.asname,
                            "line": node.lineno,
                        }
                    )
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    from_imports.append(
                        {
                            "module": node.module,
                            "name": alias.name,
                            "alias": alias.asname,
                            "line": node.lineno,
                        }
                    )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(f"{module_fqn}.{node.name}")
            elif isinstance(node, ast.ClassDef):
                classes.append(f"{module_fqn}.{node.name}")
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        global_vars.append({"name": target.id, "line": node.lineno})

        return ModuleChunk(
            fqn=module_fqn,
            project_id=self.project_id,
            file_path=str(file_path),
            start_line=1,
            end_line=len(source.split("\n")),
            ast_hash=self._compute_ast_hash(tree),
            source_code=source,
            docstring=docstring,
            imports=imports,
            from_imports=from_imports,
            functions=functions,
            classes=classes,
            global_variables=global_vars,
        )

    def _add_to_call_graph(self, caller: str, callees: List[str]):
        """Add edges to call graph"""
        if caller not in self.call_graph:
            self.call_graph.add_node(caller)

        for callee in callees:
            if callee not in self.call_graph:
                self.call_graph.add_node(callee)
            self.call_graph.add_edge(caller, callee, weight=1)

    def _get_module_fqn(self, file_path: Path) -> str:
        """Get module FQN from file path"""
        relative = file_path.relative_to(self.project_root)
        parts = list(relative.parts[:-1]) + [relative.stem]
        return ".".join(parts)

    def _compute_ast_hash(self, node: ast.AST) -> str:
        """Compute hash of AST node"""
        dump = ast.dump(node, annotate_fields=False, include_attributes=False)
        return hashlib.sha256(dump.encode()).hexdigest()[:16]

    def save_call_graph(self, output_dir: Path):
        """Save call graph to disk"""
        output_dir.mkdir(parents=True, exist_ok=True)
        nx.write_graphml(self.call_graph, output_dir / "static_call_graph.graphml")

        import pickle

        with open(output_dir / "static_call_graph.pkl", "wb") as f:
            pickle.dump(self.call_graph, f)

    def _detect_bottleneck_marker_before(self, full_source: str, func_start_lineno: int) -> bool:
        """
        Return True if the line immediately above the function start contains '# [/BOTTLENECK]'.
        We compare after stripping leading '#' and whitespace to tolerate spaces.
        """
        lines = full_source.splitlines()
        prev_idx = func_start_lineno - 2  # ast lineno is 1-based; list is 0-based
        if prev_idx < 0 or prev_idx >= len(lines):
            return False
        prev = lines[prev_idx].lstrip()
        if not prev.startswith("#"):
            return False
        token = prev[1:].strip()  # drop '#', then strip
        return token.startswith("[/BOTTLENECK]")