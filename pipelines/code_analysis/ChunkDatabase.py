# ChunkDatabase.py (complete file with all methods)
import sqlite3
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime


class ChunkDatabase:
    """SQLite database for storing code chunks with full reconstruction support"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = None
        self._connect()
        self._create_tables()

    def _connect(self):
        """Connect to the database"""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        logging.info(f"Connected to database: {self.db_path}")

    def _create_tables(self):
        """Create database tables if they don't exist"""
        cursor = self.conn.cursor()

        # Projects table
        cursor.execute(
            """
                       CREATE TABLE IF NOT EXISTS projects (
                                                               project_id TEXT PRIMARY KEY,
                                                               project_name TEXT NOT NULL,
                                                               project_hash TEXT NOT NULL,
                                                               last_parsed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                                               file_count INTEGER,
                                                               chunk_count INTEGER,
                                                               project_root TEXT
                       )
                       """
        )

        # Files table - stores complete file information
        cursor.execute(
            """
                       CREATE TABLE IF NOT EXISTS files (
                                                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                            project_id TEXT NOT NULL,
                                                            file_path TEXT NOT NULL,  -- relative to project root
                                                            original_source TEXT NOT NULL,  -- complete original file content
                                                            file_hash TEXT NOT NULL,
                                                            total_lines INTEGER NOT NULL,
                                                            encoding TEXT DEFAULT 'utf-8',
                                                            UNIQUE(project_id, file_path),
                           FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                           )
                       """
        )

        # Main chunks table with position info
        cursor.execute(
            """
                       CREATE TABLE IF NOT EXISTS chunks (
                                                             id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                             chunk_type TEXT NOT NULL,  -- 'function', 'class', 'module'
                                                             fqn TEXT NOT NULL,
                                                             project_id TEXT NOT NULL,
                                                             file_id INTEGER,
                                                             file_path TEXT NOT NULL,
                                                             start_line INTEGER NOT NULL,
                                                             end_line INTEGER NOT NULL,
                                                             start_col INTEGER DEFAULT 0,
                                                             end_col INTEGER DEFAULT -1,
                                                             indentation_level INTEGER DEFAULT 0,
                                                             position_in_parent INTEGER NOT NULL,  -- order within parent (file/class)
                                                             parent_fqn TEXT,  -- FQN of parent (for methods in classes)
                                                             ast_hash TEXT NOT NULL,
                                                             source_code TEXT NOT NULL,
                                                             version INTEGER NOT NULL DEFAULT 0,
                                                             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                                             is_active BOOLEAN DEFAULT TRUE,  -- for soft delete/versioning
                                                             UNIQUE(fqn, project_id, version),
                           FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                           )
                       """
        )

        # File structure table - tracks all elements in order
        cursor.execute(
            """
                       CREATE TABLE IF NOT EXISTS file_structure (
                                                                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                     file_id INTEGER NOT NULL,
                                                                     project_id TEXT NOT NULL,
                                                                     element_type TEXT NOT NULL,  -- 'import', 'from_import', 'function', 'class', 'global_var', 'comment_block', 'blank_lines'
                                                                     element_fqn TEXT,  -- FQN if it's a chunk, NULL otherwise
                                                                     element_content TEXT,  -- actual content if not a chunk
                                                                     start_line INTEGER NOT NULL,
                                                                     end_line INTEGER NOT NULL,
                                                                     position INTEGER NOT NULL,  -- absolute order in file
                                                                     parent_class_fqn TEXT,  -- if this element is inside a class
                                                                     FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                           FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                           )
                       """
        )

        # Functions table with additional metadata
        cursor.execute(
            """
                       CREATE TABLE IF NOT EXISTS functions (
                                                                chunk_id INTEGER PRIMARY KEY,
                                                                signature TEXT,
                                                                decorators TEXT,  -- JSON array
                                                                decorators_code TEXT,  -- JSON array of actual decorator code
                                                                docstring TEXT,
                                                                imports_needed TEXT,  -- JSON array of imports this function needs
                                                                called_functions TEXT,  -- JSON array
                                                                parameters TEXT,  -- JSON array
                                                                return_annotation TEXT,
                                                                is_async BOOLEAN,
                                                                is_method BOOLEAN,
                                                                is_staticmethod BOOLEAN,
                                                                is_classmethod BOOLEAN,
                                                                is_property BOOLEAN,
                                                                class_name TEXT,
                                                                module_name TEXT,
                                                                FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
                           )
                       """
        )

        # Classes table
        cursor.execute(
            """
                       CREATE TABLE IF NOT EXISTS classes (
                                                              chunk_id INTEGER PRIMARY KEY,
                                                              decorators TEXT,  -- JSON array
                                                              decorators_code TEXT,  -- JSON array
                                                              docstring TEXT,
                                                              base_classes TEXT,  -- JSON array
                                                              base_classes_code TEXT,  -- JSON array
                                                              methods TEXT,  -- JSON array of method FQNs
                                                              method_positions TEXT,  -- JSON dict of method positions
                                                              class_attributes TEXT,  -- JSON array
                                                              instance_attributes TEXT,  -- JSON array (from __init__)
                                                              imports_needed TEXT,  -- JSON array
                                                              module_name TEXT,
                                                              metaclass TEXT,
                                                              FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
                           )
                       """
        )

        # Modules table
        cursor.execute(
            """
                       CREATE TABLE IF NOT EXISTS modules (
                                                              chunk_id INTEGER PRIMARY KEY,
                                                              docstring TEXT,
                                                              imports TEXT,  -- JSON array with position info
                                                              from_imports TEXT,  -- JSON array with position info
                                                              functions TEXT,  -- JSON array of FQNs
                                                              classes TEXT,  -- JSON array of FQNs
                                                              global_variables TEXT,  -- JSON array with values
                                                              shebang TEXT,  -- #!/usr/bin/env python etc
                                                              encoding_declaration TEXT,  -- # -*- coding: utf-8 -*-
                                                              future_imports TEXT,  -- JSON array
                                                              module_level_code TEXT,  -- JSON array of non-function/class code
                                                              FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
                           )
                       """
        )

        # Inter-chunk code segments (code between functions/classes)
        cursor.execute(
            """
                       CREATE TABLE IF NOT EXISTS code_segments (
                                                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                    file_id INTEGER NOT NULL,
                                                                    project_id TEXT NOT NULL,
                                                                    segment_type TEXT NOT NULL,  -- 'between_chunks', 'file_header', 'file_footer'
                                                                    content TEXT NOT NULL,
                                                                    start_line INTEGER NOT NULL,
                                                                    end_line INTEGER NOT NULL,
                                                                    before_chunk_fqn TEXT,  -- chunk that comes after this segment
                                                                    after_chunk_fqn TEXT,   -- chunk that comes before this segment
                                                                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                           FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
                           )
                       """
        )

        # Create indexes for performance
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_project_version ON chunks(project_id, version)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_fqn_version ON chunks(fqn, version)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_id)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_parent ON chunks(parent_fqn)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_file_struct_file ON file_structure(file_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_file_struct_position ON file_structure(file_id, position)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_segments_file ON code_segments(file_id)"
        )

        self.conn.commit()
        logging.info("Database tables created/verified")

    def get_project_hash(self, project_id: str) -> Optional[str]:
        """Get the stored hash for a project"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT project_hash FROM projects WHERE project_id = ?", (project_id,)
        )
        row = cursor.fetchone()
        return row["project_hash"] if row else None

    def update_project(
        self,
        project_id: str,
        project_name: str,
        project_hash: str,
        file_count: int,
        chunk_count: int,
    ):
        """Update or insert project metadata"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO projects 
            (project_id, project_name, project_hash, last_parsed, file_count, chunk_count)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
        """,
            (project_id, project_name, project_hash, file_count, chunk_count),
        )
        self.conn.commit()

    def clear_project_data(self, project_id: str):
        """Clear all data for a project"""
        cursor = self.conn.cursor()

        # Delete chunks (cascades to functions, classes, modules tables)
        cursor.execute("DELETE FROM chunks WHERE project_id = ?", (project_id,))

        # Delete files (cascades to file_structure and code_segments)
        cursor.execute("DELETE FROM files WHERE project_id = ?", (project_id,))

        # Delete project entry
        cursor.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))

        self.conn.commit()
        logging.info(f"Cleared all data for project {project_id}")

    def insert_file_info(self, file_info: "FileInfo", project_id: str) -> int:
        """Insert file information"""
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO files 
            (project_id, file_path, original_source, file_hash, total_lines, encoding)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                project_id,
                file_info.file_path,
                file_info.original_source,
                file_info.file_hash,
                file_info.total_lines,
                file_info.encoding,
            ),
        )

        self.conn.commit()
        return cursor.lastrowid

    def insert_file_element(
        self, element: "FileElement", file_info: "FileInfo", project_id: str
    ):
        """Insert a file element"""
        cursor = self.conn.cursor()

        # Get file_id
        cursor.execute(
            "SELECT id FROM files WHERE project_id = ? AND file_path = ?",
            (project_id, file_info.file_path),
        )
        row = cursor.fetchone()
        if not row:
            logging.error(f"File not found in database: {file_info.file_path}")
            return

        file_id = row["id"]

        cursor.execute(
            """
                       INSERT INTO file_structure
                       (file_id, project_id, element_type, element_fqn, element_content,
                        start_line, end_line, position, parent_class_fqn)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       """,
            (
                file_id,
                project_id,
                element.element_type,
                element.element_fqn,
                element.element_content,
                element.start_line,
                element.end_line,
                element.position,
                element.parent_class_fqn,
            ),
        )

        self.conn.commit()

    def insert_code_segment(
        self, segment: "CodeSegment", file_info: "FileInfo", project_id: str
    ):
        """Insert a code segment"""
        cursor = self.conn.cursor()

        # Get file_id
        cursor.execute(
            "SELECT id FROM files WHERE project_id = ? AND file_path = ?",
            (project_id, file_info.file_path),
        )
        row = cursor.fetchone()
        if not row:
            logging.error(f"File not found in database: {file_info.file_path}")
            return

        file_id = row["id"]

        cursor.execute(
            """
                       INSERT INTO code_segments
                       (file_id, project_id, segment_type, content, start_line, end_line,
                        before_chunk_fqn, after_chunk_fqn)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       """,
            (
                file_id,
                project_id,
                segment.segment_type,
                segment.content,
                segment.start_line,
                segment.end_line,
                segment.before_chunk_fqn,
                segment.after_chunk_fqn,
            ),
        )

        self.conn.commit()

    def insert_chunk(self, chunk: "CodeChunk") -> int:
        """Insert a code chunk into the database"""
        cursor = self.conn.cursor()

        # Get file_id if we have file_info
        file_id = None
        if hasattr(chunk, "file_info") and chunk.file_info:
            cursor.execute(
                "SELECT id FROM files WHERE project_id = ? AND file_path = ?",
                (chunk.project_id, chunk.file_info.file_path),
            )
            row = cursor.fetchone()
            if row:
                file_id = row["id"]

        # Insert into main chunks table
        cursor.execute(
            """
                       INSERT INTO chunks (chunk_type, fqn, project_id, file_id, file_path,
                                           start_line, end_line, start_col, end_col,
                                           indentation_level, position_in_parent, parent_fqn,
                                           ast_hash, source_code, version)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       """,
            (
                chunk.chunk_type,
                chunk.fqn,
                chunk.project_id,
                file_id,
                chunk.file_path,
                chunk.start_line,
                chunk.end_line,
                getattr(chunk, "start_col", 0),
                getattr(chunk, "end_col", -1),
                getattr(chunk, "indentation_level", 0),
                getattr(chunk, "position_in_parent", 0),
                getattr(chunk, "parent_fqn", None),
                chunk.ast_hash,
                chunk.source_code,
                chunk.version,
            ),
        )

        chunk_id = cursor.lastrowid

        # Insert type-specific data
        if chunk.chunk_type == "function":
            self._insert_function_data(cursor, chunk_id, chunk)
        elif chunk.chunk_type == "class":
            self._insert_class_data(cursor, chunk_id, chunk)
        elif chunk.chunk_type == "module":
            self._insert_module_data(cursor, chunk_id, chunk)

        self.conn.commit()
        return chunk_id

    def _insert_function_data(self, cursor, chunk_id: int, chunk: "FunctionChunk"):
        """Insert function-specific data"""
        cursor.execute(
            """
                       INSERT INTO functions (chunk_id, signature, decorators, decorators_code,
                                              docstring, imports_needed, called_functions, parameters,
                                              return_annotation, is_async, is_method, is_staticmethod,
                                              is_classmethod, is_property, class_name, module_name)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       """,
            (
                chunk_id,
                chunk.signature,
                json.dumps(chunk.decorators),
                json.dumps(getattr(chunk, "decorators_code", [])),
                chunk.docstring,
                json.dumps(getattr(chunk, "imports_needed", [])),
                json.dumps(chunk.called_functions),
                json.dumps(chunk.parameters),
                chunk.return_annotation,
                chunk.is_async,
                chunk.is_method,
                getattr(chunk, "is_staticmethod", False),
                getattr(chunk, "is_classmethod", False),
                getattr(chunk, "is_property", False),
                chunk.class_name,
                chunk.module_name,
            ),
        )

    def _insert_class_data(self, cursor, chunk_id: int, chunk: "ClassChunk"):
        """Insert class-specific data"""
        cursor.execute(
            """
                       INSERT INTO classes (chunk_id, decorators, decorators_code, docstring,
                                            base_classes, base_classes_code, methods, method_positions,
                                            class_attributes, instance_attributes, imports_needed,
                                            module_name, metaclass)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       """,
            (
                chunk_id,
                json.dumps(chunk.decorators),
                json.dumps(getattr(chunk, "decorators_code", [])),
                chunk.docstring,
                json.dumps(chunk.base_classes),
                json.dumps(getattr(chunk, "base_classes_code", [])),
                json.dumps(chunk.methods),
                json.dumps(getattr(chunk, "method_positions", {})),
                json.dumps(chunk.class_attributes),
                json.dumps(getattr(chunk, "instance_attributes", [])),
                json.dumps(getattr(chunk, "imports_needed", [])),
                chunk.module_name,
                getattr(chunk, "metaclass", None),
            ),
        )

    def _insert_module_data(self, cursor, chunk_id: int, chunk: "ModuleChunk"):
        """Insert module-specific data"""
        cursor.execute(
            """
                       INSERT INTO modules (chunk_id, docstring, imports, from_imports,
                                            functions, classes, global_variables, shebang,
                                            encoding_declaration, future_imports, module_level_code)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       """,
            (
                chunk_id,
                chunk.docstring,
                json.dumps(getattr(chunk, "imports", [])),
                json.dumps(getattr(chunk, "from_imports", [])),
                json.dumps(chunk.functions),
                json.dumps(chunk.classes),
                json.dumps(getattr(chunk, "global_variables", [])),
                getattr(chunk, "shebang", None),
                getattr(chunk, "encoding_declaration", None),
                json.dumps(getattr(chunk, "future_imports", [])),
                json.dumps(getattr(chunk, "module_level_code", [])),
            ),
        )

    def insert_chunks(self, chunks: List["CodeChunk"]) -> None:
        """Insert multiple chunks"""
        for chunk in chunks:
            try:
                self.insert_chunk(chunk)
            except sqlite3.IntegrityError as e:
                logging.warning(f"Chunk already exists: {chunk.fqn} v{chunk.version}")
            except Exception as e:
                logging.error(f"Failed to insert chunk {chunk.fqn}: {e}")

    def get_chunk_by_fqn(
        self, fqn: str, project_id: str, version: int = 0
    ) -> Optional[Dict[str, Any]]:
        """Get a chunk by its FQN"""
        cursor = self.conn.cursor()

        cursor.execute(
            """
                       SELECT c.*,
                              f.*,
                              cl.*,
                              m.*
                       FROM chunks c
                                LEFT JOIN functions f ON c.id = f.chunk_id
                                LEFT JOIN classes cl ON c.id = cl.chunk_id
                                LEFT JOIN modules m ON c.id = m.chunk_id
                       WHERE c.fqn = ? AND c.project_id = ? AND c.version = ?
                       """,
            (fqn, project_id, version),
        )

        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def get_chunks_by_project(
        self, project_id: str, chunk_type: Optional[str] = None, version: int = 0
    ) -> List[Dict[str, Any]]:
        """Get all chunks for a project"""
        cursor = self.conn.cursor()

        query = """
                SELECT c.*,
                       f.*,
                       cl.*,
                       m.*
                FROM chunks c
                         LEFT JOIN functions f ON c.id = f.chunk_id
                         LEFT JOIN classes cl ON c.id = cl.chunk_id
                         LEFT JOIN modules m ON c.id = m.chunk_id
                WHERE c.project_id = ? AND c.version = ? \
                """

        params = [project_id, version]

        if chunk_type:
            query += " AND c.chunk_type = ?"
            params.append(chunk_type)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def search_chunks(
        self, query: str, project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for chunks by name pattern"""
        cursor = self.conn.cursor()

        sql = """
              SELECT c.*,
                     f.*,
                     cl.*,
                     m.*
              FROM chunks c
                       LEFT JOIN functions f ON c.id = f.chunk_id
                       LEFT JOIN classes cl ON c.id = cl.chunk_id
                       LEFT JOIN modules m ON c.id = m.chunk_id
              WHERE c.fqn LIKE ? \
              """

        params = [f"%{query}%"]

        if project_id:
            sql += " AND c.project_id = ?"
            params.append(project_id)

        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logging.info("Database connection closed")
