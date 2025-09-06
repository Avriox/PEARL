# CodeAnalyzer.py (renamed from CodeParser.py)
import ast
import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, asdict, field
import astroid
import astor
import networkx as nx
import radon.complexity as radon_cc
import radon.metrics as radon_metrics
import radon.raw as radon_raw


@dataclass
class StaticFeatures:
    cyclomatic_complexity: int = 0
    cognitive_complexity: int = 0
    maintainability_index: float = 0.0
    loc: int = 0
    sloc: int = 0
    loop_count: int = 0
    max_nesting_depth: int = 0
    loops: List[Dict] = field(default_factory=list)
    has_nested_loops: bool = False
    list_operations: int = 0
    dict_operations: int = 0
    set_operations: int = 0
    tuple_operations: int = 0
    comprehensions: int = 0
    subscript_in_loops: int = 0
    uses_threading: bool = False
    uses_multiprocessing: bool = False
    uses_asyncio: bool = False
    concurrency_primitives: List[str] = field(default_factory=list)
    numpy_calls: int = 0
    pandas_calls: int = 0
    regex_operations: int = 0
    db_operations: int = 0
    http_operations: int = 0
    external_calls: Dict[str, int] = field(default_factory=dict)
    calls_made: List[str] = field(default_factory=list)
    call_count: int = 0


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
        """Process function and analyze it in one go"""

        # Build FQN
        func_name = node.name
        if class_name:
            fqn = f"{module_fqn}.{class_name}.{func_name}"
            is_method = True
        else:
            fqn = f"{module_fqn}.{func_name}"
            is_method = False

        # Extract basic info
        decorators = [astor.to_source(d).strip() for d in node.decorator_list]
        docstring = ast.get_docstring(node)
        parameters = [arg.arg for arg in node.args.args]

        # Get return annotation
        return_annotation = None
        if node.returns:
            return_annotation = astor.to_source(node.returns).strip()

        # Build signature
        signature = f"{func_name}({', '.join(parameters)})"
        if return_annotation:
            signature += f" -> {return_annotation}"

        # Extract source code
        source_lines = source.split("\n")
        func_source = "\n".join(source_lines[node.lineno - 1 : node.end_lineno])

        # Perform static analysis on this function's AST
        static_features = self._analyze_function_ast(node, func_source, module_fqn)

        # Check for special decorators
        is_staticmethod = any("staticmethod" in d for d in decorators)
        is_classmethod = any("classmethod" in d for d in decorators)
        is_property = any("property" in d for d in decorators)

        return FunctionChunk(
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

        # Extract class info
        decorators = [astor.to_source(d).strip() for d in node.decorator_list]
        base_classes = [astor.to_source(b).strip() for b in node.bases]
        docstring = ast.get_docstring(node)

        # Extract class attributes and methods
        methods = []
        method_chunks = []
        class_attributes = []

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_fqn = f"{fqn}.{item.name}"
                methods.append(method_fqn)

                # Process method
                method_chunk = self._process_function(
                    item, source, file_path, module_fqn, class_name, module_tree
                )
                method_chunks.append(method_chunk)

            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        class_attributes.append(target.id)

        # Get class source
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
        self, node: ast.AST, source_code: str, module_fqn: str
    ) -> StaticFeatures:
        """Analyze a function's AST node for static features"""

        features = StaticFeatures()

        # Complexity metrics
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
        except:
            pass

        # Analyze loops
        loop_info = self._analyze_loops(node)
        features.loop_count = loop_info["count"]
        features.max_nesting_depth = loop_info["max_depth"]
        features.has_nested_loops = loop_info["has_nested"]
        features.loops = loop_info["loops"]

        # Analyze data structures
        data_usage = self._analyze_data_structures(node, loop_info["loop_nodes"])
        features.list_operations = data_usage["list"]
        features.dict_operations = data_usage["dict"]
        features.set_operations = data_usage["set"]
        features.tuple_operations = data_usage["tuple"]
        features.comprehensions = data_usage["comprehensions"]
        features.subscript_in_loops = data_usage["subscript_in_loops"]

        # Detect external calls and concurrency
        external = self._detect_external_calls(node)
        features.numpy_calls = external["numpy"]
        features.pandas_calls = external["pandas"]
        features.regex_operations = external["regex"]
        features.db_operations = external["database"]
        features.http_operations = external["http"]
        features.external_calls = external["all_external"]

        concurrency = self._detect_concurrency(node, source_code)
        features.uses_threading = concurrency["threading"]
        features.uses_multiprocessing = concurrency["multiprocessing"]
        features.uses_asyncio = concurrency["asyncio"]
        features.concurrency_primitives = concurrency["primitives"]

        # Extract calls
        calls = self._extract_calls(node, module_fqn)
        features.calls_made = calls["direct_calls"]
        features.call_count = calls["count"]

        # Cognitive complexity
        features.cognitive_complexity = self._estimate_cognitive_complexity(node)

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

    def _extract_calls(self, node: ast.AST, module_fqn: str) -> Dict:
        """Extract function calls"""
        direct_calls = []

        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                if isinstance(n.func, ast.Name):
                    direct_calls.append(f"{module_fqn}.{n.func.id}")
                elif isinstance(n.func, ast.Attribute):
                    if isinstance(n.func.value, ast.Name):
                        direct_calls.append(f"{n.func.value.id}.{n.func.attr}")

        return {"direct_calls": list(set(direct_calls)), "count": len(direct_calls)}

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
