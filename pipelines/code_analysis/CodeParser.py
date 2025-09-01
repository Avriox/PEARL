# CodeParser.py
import ast
import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, asdict, field
import astroid
from astroid import nodes
import astor  # or astunparse


@dataclass
class FileInfo:
    """Complete file information for reconstruction"""

    file_path: str  # relative to project root
    original_source: str
    file_hash: str
    total_lines: int
    encoding: str = "utf-8"
    shebang: Optional[str] = None
    encoding_declaration: Optional[str] = None


@dataclass
class FileElement:
    """Represents any element in a file (for ordering)"""

    element_type: str  # 'import', 'function', 'class', etc.
    element_fqn: Optional[str]  # FQN if it's a chunk
    element_content: Optional[str]  # actual content if not a chunk
    start_line: int
    end_line: int
    position: int  # order in file
    parent_class_fqn: Optional[str] = None


@dataclass
class CodeSegment:
    """Code between chunks"""

    segment_type: str
    content: str
    start_line: int
    end_line: int
    before_chunk_fqn: Optional[str] = None
    after_chunk_fqn: Optional[str] = None


@dataclass
class CodeChunk:
    """Base class for all code chunks"""

    chunk_type: str
    fqn: str
    project_id: str
    file_path: str
    start_line: int
    end_line: int
    ast_hash: str
    source_code: str
    version: int = 0
    start_col: int = 0
    end_col: int = -1
    indentation_level: int = 0
    position_in_parent: int = 0  # order within parent
    parent_fqn: Optional[str] = None
    file_info: Optional[FileInfo] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FunctionChunk(CodeChunk):
    """Represents a function or method"""

    chunk_type: str = field(default="function", init=False)
    signature: str = ""
    decorators: List[str] = field(default_factory=list)
    decorators_code: List[str] = field(default_factory=list)  # actual decorator code
    docstring: Optional[str] = None
    imports_needed: List[str] = field(
        default_factory=list
    )  # imports this function requires
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


@dataclass
class ClassChunk(CodeChunk):
    """Represents a class"""

    chunk_type: str = field(default="class", init=False)
    decorators: List[str] = field(default_factory=list)
    decorators_code: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    base_classes: List[str] = field(default_factory=list)
    base_classes_code: List[str] = field(default_factory=list)  # actual base class code
    methods: List[str] = field(default_factory=list)  # FQNs of methods in order
    method_positions: Dict[str, int] = field(
        default_factory=dict
    )  # method_name -> position
    class_attributes: List[str] = field(default_factory=list)
    instance_attributes: List[str] = field(default_factory=list)
    imports_needed: List[str] = field(default_factory=list)
    module_name: str = ""
    metaclass: Optional[str] = None


@dataclass
class ModuleChunk(CodeChunk):
    """Represents an entire module"""

    chunk_type: str = field(default="module", init=False)
    docstring: Optional[str] = None
    imports: List[Dict[str, Any]] = field(default_factory=list)  # with line numbers
    from_imports: List[Dict[str, Any]] = field(
        default_factory=list
    )  # with line numbers
    functions: List[str] = field(default_factory=list)  # FQNs in order
    classes: List[str] = field(default_factory=list)  # FQNs in order
    global_variables: List[Dict[str, Any]] = field(
        default_factory=list
    )  # with values and positions
    module_level_code: List[Dict[str, Any]] = field(
        default_factory=list
    )  # non-function/class code
    future_imports: List[str] = field(default_factory=list)
    shebang: Optional[str] = None
    encoding_declaration: Optional[str] = None


@dataclass
class ParsedFile:
    """Complete parsed file with all elements"""

    file_info: FileInfo
    chunks: List[CodeChunk]
    file_elements: List[FileElement]
    code_segments: List[CodeSegment]


class CodeParser:
    """Parser for extracting code chunks from Python files"""

    def __init__(self, project_id: str, project_root: Path):
        self.project_id = project_id
        self.project_root = Path(project_root)
        self.chunks: List[CodeChunk] = []
        self.parsed_files: List[ParsedFile] = []
        self.module_imports: Dict[str, List[str]] = {}

    def parse_project(self) -> Tuple[List[CodeChunk], List[ParsedFile]]:
        """Parse all Python files in the project"""
        logging.info(f"Parsing project {self.project_id} at {self.project_root}")

        python_files = list(self.project_root.rglob("*.py"))
        logging.info(f"Found {len(python_files)} Python files")

        for py_file in python_files:
            if (
                ".venv" in str(py_file)
                or "__pycache__" in str(py_file)
                or "run_logs" in str(py_file)
            ):
                continue

            try:
                parsed_file = self.parse_file(py_file)
                if parsed_file:
                    self.parsed_files.append(parsed_file)
            except Exception as e:
                logging.error(f"Failed to parse {py_file}: {e}")

        return self.chunks, self.parsed_files

    def parse_file(self, file_path: Path) -> Optional[ParsedFile]:
        """Parse a single Python file with full reconstruction info"""
        logging.debug(f"Parsing file: {file_path}")

        # Read file content
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source_code = f.read()
        except UnicodeDecodeError:
            # Try with different encoding
            with open(file_path, "r", encoding="latin-1") as f:
                source_code = f.read()
                encoding = "latin-1"
        else:
            encoding = "utf-8"

        source_lines = source_code.split("\n")

        # Check for shebang and encoding declaration
        shebang = None
        encoding_declaration = None

        if source_lines and source_lines[0].startswith("#!"):
            shebang = source_lines[0]

        for line in source_lines[:2]:  # Check first two lines
            if "coding:" in line or "coding=" in line:
                encoding_declaration = line
                break

        # Create file info
        relative_path = file_path.relative_to(self.project_root)
        file_hash = hashlib.sha256(source_code.encode()).hexdigest()

        file_info = FileInfo(
            file_path=str(relative_path),
            original_source=source_code,
            file_hash=file_hash,
            total_lines=len(source_lines),
            encoding=encoding,
            shebang=shebang,
            encoding_declaration=encoding_declaration,
        )

        # Parse with ast
        try:
            tree = ast.parse(source_code, filename=str(file_path))
        except SyntaxError as e:
            logging.error(f"Syntax error in {file_path}: {e}")
            return None

        # Parse with astroid for semantic analysis
        try:
            astroid_module = astroid.parse(
                source_code, module_name=self._get_module_name(file_path)
            )
        except Exception as e:
            logging.warning(f"Astroid parsing failed for {file_path}: {e}")
            astroid_module = None

        # Extract all elements in file
        module_fqn = self._get_module_fqn(file_path)
        file_elements = []
        code_segments = []
        file_chunks = []

        # Extract module-level information first
        module_chunk = self._create_module_chunk(
            tree, source_code, file_path, module_fqn, file_info, source_lines
        )
        self.chunks.append(module_chunk)
        file_chunks.append(module_chunk)

        # Process all top-level nodes in order
        position = 0
        last_line = 0

        for node in tree.body:
            # Check for code/comments between nodes
            if node.lineno > last_line + 1:
                segment = self._extract_code_segment(
                    source_lines, last_line + 1, node.lineno - 1, "between_chunks"
                )
                if segment:
                    code_segments.append(segment)

            # Process the node
            if isinstance(node, ast.Import):
                element = FileElement(
                    element_type="import",
                    element_fqn=None,
                    element_content=astor.to_source(node).strip(),
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    position=position,
                )
                file_elements.append(element)

            elif isinstance(node, ast.ImportFrom):
                element = FileElement(
                    element_type="from_import",
                    element_fqn=None,
                    element_content=astor.to_source(node).strip(),
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    position=position,
                )
                file_elements.append(element)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_chunk = self._process_function(
                    node,
                    source_code,
                    file_path,
                    module_fqn,
                    None,
                    astroid_module,
                    position,
                    source_lines,
                    file_info,
                )
                file_chunks.append(func_chunk)

                element = FileElement(
                    element_type="function",
                    element_fqn=func_chunk.fqn,
                    element_content=None,  # Content is in chunk
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    position=position,
                )
                file_elements.append(element)

            elif isinstance(node, ast.ClassDef):
                class_chunk = self._process_class(
                    node,
                    source_code,
                    file_path,
                    module_fqn,
                    astroid_module,
                    position,
                    source_lines,
                    file_info,
                )
                file_chunks.append(class_chunk)

                element = FileElement(
                    element_type="class",
                    element_fqn=class_chunk.fqn,
                    element_content=None,  # Content is in chunk
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    position=position,
                )
                file_elements.append(element)

            elif isinstance(node, ast.Assign):
                # Global variable
                element = FileElement(
                    element_type="global_var",
                    element_fqn=None,
                    element_content=astor.to_source(node).strip(),
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    position=position,
                )
                file_elements.append(element)

            else:
                # Other module-level code
                element = FileElement(
                    element_type="module_code",
                    element_fqn=None,
                    element_content=astor.to_source(node).strip(),
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    position=position,
                )
                file_elements.append(element)

            position += 1
            last_line = node.end_lineno or node.lineno

        # Check for trailing code
        if last_line < len(source_lines):
            segment = self._extract_code_segment(
                source_lines, last_line + 1, len(source_lines), "file_footer"
            )
            if segment:
                code_segments.append(segment)

        parsed_file = ParsedFile(
            file_info=file_info,
            chunks=file_chunks,
            file_elements=file_elements,
            code_segments=code_segments,
        )

        return parsed_file

    def _get_module_name(self, file_path: Path) -> str:
        """Get module name from file path"""
        relative_path = file_path.relative_to(self.project_root)
        module_parts = list(relative_path.parts[:-1]) + [relative_path.stem]
        return ".".join(module_parts)

    def _get_module_fqn(self, file_path: Path) -> str:
        """Get fully qualified module name"""
        return self._get_module_name(file_path)

    def _get_indentation_level(self, lines: List[str], line_no: int) -> int:
        """Get indentation level of a line"""
        if line_no <= 0 or line_no > len(lines):
            return 0
        line = lines[line_no - 1]
        return len(line) - len(line.lstrip())

    def _extract_decorators_code(self, node: ast.AST, lines: List[str]) -> List[str]:
        """Extract actual decorator code lines"""
        decorator_codes = []
        for decorator in node.decorator_list:
            start = decorator.lineno - 1
            end = decorator.end_lineno or decorator.lineno
            decorator_code = "\n".join(lines[start:end])
            decorator_codes.append(decorator_code.strip())
        return decorator_codes

    def _extract_code_segment(
        self, lines: List[str], start: int, end: int, segment_type: str
    ) -> Optional[CodeSegment]:
        """Extract code between chunks"""
        if start > end or start < 1:
            return None

        content = "\n".join(lines[start - 1 : end])
        if not content.strip():  # Skip empty segments
            return None

        return CodeSegment(
            segment_type=segment_type, content=content, start_line=start, end_line=end
        )

    def _compute_ast_hash(self, node: ast.AST) -> str:
        """Compute a stable hash of an AST node"""
        ast_dump = ast.dump(node, annotate_fields=False, include_attributes=False)
        return hashlib.sha256(ast_dump.encode()).hexdigest()[:16]

    def _get_source_segment(
        self, source: str, node: ast.AST, lines: List[str] = None
    ) -> str:
        """Extract source code for a node"""
        if lines is None:
            lines = source.split("\n")

        start_line = node.lineno - 1
        end_line = getattr(node, "end_lineno", node.lineno)

        # Get column info if available
        start_col = getattr(node, "col_offset", 0)
        end_col = getattr(node, "end_col_offset", -1)

        if start_line < len(lines) and end_line <= len(lines):
            segment_lines = lines[start_line:end_line]
            if segment_lines:
                # Apply column offsets if available
                if start_col > 0 and len(segment_lines) == 1:
                    segment_lines[0] = segment_lines[0][start_col:]
                if end_col > -1 and len(segment_lines) == 1:
                    segment_lines[0] = segment_lines[0][:end_col]

            return "\n".join(segment_lines)

        # Fallback to unparsing
        try:
            return astor.to_source(node)
        except:
            return ""

    def _process_function(
        self,
        node: ast.AST,
        source: str,
        file_path: Path,
        module_fqn: str,
        class_name: Optional[str],
        astroid_module: Optional[nodes.Module],
        position: int,
        lines: List[str],
        file_info: FileInfo,
    ) -> FunctionChunk:
        """Process a function definition with full reconstruction info"""
        func_name = node.name

        # Build FQN
        if class_name:
            fqn = f"{module_fqn}.{class_name}.{func_name}"
            is_method = True
            parent_fqn = f"{module_fqn}.{class_name}"
        else:
            fqn = f"{module_fqn}.{func_name}"
            is_method = False
            parent_fqn = module_fqn

        # Extract decorators
        decorators = []
        decorators_code = self._extract_decorators_code(node, lines)
        for decorator in node.decorator_list:
            try:
                decorators.append(astor.to_source(decorator).strip())
            except:
                decorators.append(str(decorator))

        # Check for special decorators
        is_staticmethod = any("staticmethod" in d for d in decorators)
        is_classmethod = any("classmethod" in d for d in decorators)
        is_property = any("property" in d for d in decorators)

        # Extract parameters
        parameters = []
        for arg in node.args.args:
            parameters.append(arg.arg)

        # Extract return annotation
        return_annotation = None
        if node.returns:
            try:
                return_annotation = astor.to_source(node.returns).strip()
            except:
                return_annotation = str(node.returns)

        # Build signature
        params_str = ", ".join(parameters)
        signature = f"{func_name}({params_str})"
        if return_annotation:
            signature += f" -> {return_annotation}"

        # Extract docstring
        docstring = ast.get_docstring(node)

        # Extract called functions
        called_functions = self._extract_called_functions(node, astroid_module)

        # Get source code
        source_code = self._get_source_segment(source, node, lines)

        # Get indentation level
        indentation_level = self._get_indentation_level(lines, node.lineno)

        # Create function chunk
        chunk = FunctionChunk(
            fqn=fqn,
            project_id=self.project_id,
            file_path=str(file_path.relative_to(self.project_root)),
            file_info=file_info,
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            start_col=getattr(node, "col_offset", 0),
            end_col=getattr(node, "end_col_offset", -1),
            indentation_level=indentation_level,
            position_in_parent=position,
            parent_fqn=parent_fqn,
            ast_hash=self._compute_ast_hash(node),
            source_code=source_code,
            signature=signature,
            decorators=decorators,
            decorators_code=decorators_code,
            docstring=docstring,
            imports_needed=self._extract_function_imports(node, module_fqn),
            called_functions=called_functions,
            parameters=parameters,
            return_annotation=return_annotation,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_method=is_method,
            is_staticmethod=is_staticmethod,
            is_classmethod=is_classmethod,
            is_property=is_property,
            class_name=class_name,
            module_name=module_fqn,
        )

        self.chunks.append(chunk)
        return chunk

    def _process_class(
        self,
        node: ast.ClassDef,
        source: str,
        file_path: Path,
        module_fqn: str,
        astroid_module: Optional[nodes.Module],
        position: int,
        lines: List[str],
        file_info: FileInfo,
    ) -> ClassChunk:
        """Process a class definition with full reconstruction info"""
        class_name = node.name
        fqn = f"{module_fqn}.{class_name}"

        # Extract decorators
        decorators = []
        decorators_code = self._extract_decorators_code(node, lines)
        for decorator in node.decorator_list:
            try:
                decorators.append(astor.to_source(decorator).strip())
            except:
                decorators.append(str(decorator))

        # Extract base classes
        base_classes = []
        base_classes_code = []
        for base in node.bases:
            try:
                base_code = astor.to_source(base).strip()
                base_classes.append(base_code)
                base_classes_code.append(base_code)
            except:
                base_classes.append(str(base))
                base_classes_code.append(str(base))

        # Extract metaclass if present
        metaclass = None
        for keyword in node.keywords:
            if keyword.arg == "metaclass":
                try:
                    metaclass = astor.to_source(keyword.value).strip()
                except:
                    metaclass = str(keyword.value)

        # Extract docstring
        docstring = ast.get_docstring(node)

        # Process class body
        methods = []
        method_positions = {}
        class_attributes = []
        instance_attributes = []

        class_position = 0
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_fqn = f"{fqn}.{item.name}"
                methods.append(method_fqn)
                method_positions[item.name] = class_position

                # Process the method
                self._process_function(
                    item,
                    source,
                    file_path,
                    module_fqn,
                    class_name,
                    astroid_module,
                    class_position,
                    lines,
                    file_info,
                )

                # Extract instance attributes from __init__
                if item.name == "__init__":
                    instance_attributes.extend(self._extract_instance_attributes(item))

            elif isinstance(item, ast.Assign):
                # Class attribute
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        class_attributes.append(target.id)

            class_position += 1

        # Get source code
        source_code = self._get_source_segment(source, node, lines)

        # Get indentation level
        indentation_level = self._get_indentation_level(lines, node.lineno)

        # Create class chunk
        chunk = ClassChunk(
            fqn=fqn,
            project_id=self.project_id,
            file_path=str(file_path.relative_to(self.project_root)),
            file_info=file_info,
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            start_col=getattr(node, "col_offset", 0),
            end_col=getattr(node, "end_col_offset", -1),
            indentation_level=indentation_level,
            position_in_parent=position,
            parent_fqn=module_fqn,
            ast_hash=self._compute_ast_hash(node),
            source_code=source_code,
            decorators=decorators,
            decorators_code=decorators_code,
            docstring=docstring,
            base_classes=base_classes,
            base_classes_code=base_classes_code,
            methods=methods,
            method_positions=method_positions,
            class_attributes=class_attributes,
            instance_attributes=instance_attributes,
            imports_needed=self._extract_class_imports(node, module_fqn),
            module_name=module_fqn,
            metaclass=metaclass,
        )

        self.chunks.append(chunk)
        return chunk

    def _create_module_chunk(
        self,
        tree: ast.Module,
        source: str,
        file_path: Path,
        module_fqn: str,
        file_info: FileInfo,
        lines: List[str],
    ) -> ModuleChunk:
        """Create a module chunk with full reconstruction info"""
        docstring = ast.get_docstring(tree)

        # Extract imports with positions
        imports = []
        from_imports = []
        future_imports = []

        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(
                        {
                            "statement": f"import {alias.name}",
                            "module": alias.name,
                            "alias": alias.asname,
                            "line": node.lineno,
                        }
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                is_future = module == "__future__"

                for alias in node.names:
                    import_info = {
                        "statement": f"from {module} import {alias.name}",
                        "module": module,
                        "name": alias.name,
                        "alias": alias.asname,
                        "line": node.lineno,
                        "level": node.level,  # for relative imports
                    }

                    if is_future:
                        future_imports.append(import_info["statement"])
                    else:
                        from_imports.append(import_info)

        # Extract top-level elements in order
        functions = []
        classes = []
        global_variables = []
        module_level_code = []

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(f"{module_fqn}.{node.name}")
            elif isinstance(node, ast.ClassDef):
                classes.append(f"{module_fqn}.{node.name}")
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        try:
                            value_code = astor.to_source(node.value).strip()
                        except:
                            value_code = str(node.value)

                        global_variables.append(
                            {
                                "name": target.id,
                                "value": value_code,
                                "line": node.lineno,
                            }
                        )
            elif not isinstance(node, (ast.Import, ast.ImportFrom)):
                # Other module-level code
                try:
                    code = astor.to_source(node).strip()
                except:
                    code = str(node)

                module_level_code.append(
                    {"code": code, "line": node.lineno, "type": node.__class__.__name__}
                )

        return ModuleChunk(
            fqn=module_fqn,
            project_id=self.project_id,
            file_path=str(file_path.relative_to(self.project_root)),
            file_info=file_info,
            start_line=1,
            end_line=len(lines),
            indentation_level=0,
            position_in_parent=0,
            parent_fqn=None,
            ast_hash=self._compute_ast_hash(tree),
            source_code=source,
            docstring=docstring,
            imports=imports,
            from_imports=from_imports,
            functions=functions,
            classes=classes,
            global_variables=global_variables,
            module_level_code=module_level_code,
            future_imports=future_imports,
            shebang=file_info.shebang,
            encoding_declaration=file_info.encoding_declaration,
        )

    def _extract_called_functions(
        self, node: ast.AST, astroid_module: Optional[nodes.Module]
    ) -> List[str]:
        """Extract functions called within a function/method"""
        called = []

        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    called.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    try:
                        full_name = astor.to_source(child.func).strip()
                        called.append(full_name)
                    except:
                        called.append(child.func.attr)

        return list(set(called))

    def _extract_function_imports(self, node: ast.AST, module_fqn: str) -> List[str]:
        """Extract imports needed by a function"""
        # This is a simplified version - could be enhanced with astroid
        imports_needed = []

        # Check for common patterns
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                # Common standard library modules
                if child.id in ["os", "sys", "json", "re", "datetime", "logging"]:
                    imports_needed.append(f"import {child.id}")
            elif isinstance(child, ast.Attribute):
                # Try to identify module usage
                if isinstance(child.value, ast.Name):
                    if child.value.id in ["np", "pd", "plt"]:
                        imports_needed.append(f"import {child.value.id}")

        return list(set(imports_needed))

    def _extract_class_imports(self, node: ast.ClassDef, module_fqn: str) -> List[str]:
        """Extract imports needed by a class"""
        imports_needed = []

        # Check base classes
        for base in node.bases:
            if isinstance(base, ast.Name):
                # Could be an imported class
                imports_needed.append(f"# May need import for {base.id}")

        # Check methods
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                imports_needed.extend(self._extract_function_imports(item, module_fqn))

        return list(set(imports_needed))

    def _extract_instance_attributes(self, init_node: ast.FunctionDef) -> List[str]:
        """Extract instance attributes from __init__ method"""
        attributes = []

        for node in ast.walk(init_node):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute):
                        if (
                            isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                        ):
                            attributes.append(target.attr)

        return list(set(attributes))
