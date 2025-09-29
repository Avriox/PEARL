#!/usr/bin/env python3

import json
import ast
import os
import sys
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict


def parse_function_name(full_name: str) -> Tuple[Optional[str], str]:
    """
    Parse a full function name like 'deepdiff.diff.DeepDiff._diff_ordered_iterable_by_difflib'
    Returns (class_name, function_name) or (None, function_name) for standalone functions
    """
    parts = full_name.split(".")
    if len(parts) >= 2:
        # Check if second-to-last part looks like a class name (starts with capital)
        if len(parts) >= 3 and parts[-2][0].isupper():
            return parts[-2], parts[-1]
    return None, parts[-1]


def extract_class_and_methods(
    file_path: str, target_classes: Set[str], target_methods: Dict[str, Set[str]]
) -> Dict[str, str]:
    """
    Extract class definitions and specific methods from a Python file.
    Returns a dict mapping class_name -> extracted_code
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return {}

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"Error parsing {file_path}: {e}")
        return {}

    source_lines = source.splitlines()
    results = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name in target_classes:
            class_name = node.name
            target_methods_for_class = target_methods.get(class_name, set())

            # Get class definition line
            class_start = node.lineno - 1
            class_code_lines = []

            # Add class definition
            class_def_line = source_lines[class_start]
            class_code_lines.append(class_def_line)

            # Add class docstring if present
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                docstring_start = node.body[0].lineno - 1
                docstring_end = node.body[0].end_lineno
                for i in range(docstring_start, docstring_end):
                    class_code_lines.append(source_lines[i])
                class_code_lines.append("")

            # Find and add __init__ method if it exists
            init_added = False
            for method_node in node.body:
                if (
                    isinstance(method_node, ast.FunctionDef)
                    and method_node.name == "__init__"
                ):
                    method_start = method_node.lineno - 1
                    method_end = method_node.end_lineno
                    for i in range(method_start, method_end):
                        class_code_lines.append("    " + source_lines[i])
                    class_code_lines.append("")
                    init_added = True
                    break

            # Add target methods
            for method_node in node.body:
                if (
                    isinstance(method_node, ast.FunctionDef)
                    and method_node.name in target_methods_for_class
                    and method_node.name != "__init__"
                ):  # Don't add __init__ twice
                    method_start = method_node.lineno - 1
                    method_end = method_node.end_lineno
                    for i in range(method_start, method_end):
                        class_code_lines.append("    " + source_lines[i])
                    class_code_lines.append("")

            if class_code_lines:
                results[class_name] = "\n".join(class_code_lines)

    return results


def extract_standalone_functions(
    file_path: str, target_functions: Set[str]
) -> Dict[str, str]:
    """
    Extract standalone functions (not class methods) from a Python file.
    Returns a dict mapping function_name -> extracted_code
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return {}

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"Error parsing {file_path}: {e}")
        return {}

    source_lines = source.splitlines()
    results = {}

    # Get top-level function definitions
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in target_functions:
            func_start = node.lineno - 1
            func_end = node.end_lineno
            func_lines = []
            for i in range(func_start, func_end):
                func_lines.append(source_lines[i])
            results[node.name] = "\n".join(func_lines)

    return results


def main():
    if len(sys.argv) != 3:
        print(
            "Usage: python extract_functions_from_json.py <root_directory> <json_file>"
        )
        sys.exit(1)

    root_dir = sys.argv[1]
    json_file = sys.argv[2]
    output_file = "extracted_functions.txt"

    # Check if directories exist
    if not os.path.exists(root_dir):
        print(f"Error: Directory '{root_dir}' does not exist")
        sys.exit(1)

    if not os.path.exists(json_file):
        print(f"Error: JSON file '{json_file}' does not exist")
        sys.exit(1)

    # Load JSON data
    try:
        with open(json_file, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        sys.exit(1)

    # Organize data by file
    files_data = defaultdict(list)
    for item in data:
        full_name = item["c0"]
        file_path = item["c1"]
        files_data[file_path].append(full_name)

    # Clear output file
    with open(output_file, "w") as f:
        f.write("")

    # Process each file
    for rel_file_path, function_names in files_data.items():
        full_file_path = os.path.join(root_dir, rel_file_path)

        if not os.path.exists(full_file_path):
            print(f"Warning: File {full_file_path} not found, skipping...")
            continue

        print(f"Processing {rel_file_path}...")

        # Organize functions by class vs standalone
        classes_to_methods = defaultdict(set)
        standalone_functions = set()
        all_classes = set()

        for full_name in function_names:
            class_name, func_name = parse_function_name(full_name)
            if class_name:
                classes_to_methods[class_name].add(func_name)
                all_classes.add(class_name)
            else:
                standalone_functions.add(func_name)

        # Extract code
        class_results = extract_class_and_methods(
            full_file_path, all_classes, classes_to_methods
        )
        function_results = extract_standalone_functions(
            full_file_path, standalone_functions
        )

        # Write to output file
        if class_results or function_results:
            with open(output_file, "a") as f:
                f.write(f"=== {rel_file_path} ===\n\n")

                # Write classes first
                for class_name in sorted(class_results.keys()):
                    f.write(class_results[class_name])
                    f.write("\n\n")

                # Write standalone functions
                for func_name in sorted(function_results.keys()):
                    f.write(function_results[func_name])
                    f.write("\n\n")

                f.write("\n")

    print(f"Functions extracted to {output_file}")


if __name__ == "__main__":
    main()
