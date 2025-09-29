#!/bin/sh

# Check if root directory parameter is provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <root_directory>"
    exit 1
fi

root_dir="$1"
output_file="combined_python_files.txt"

# Check if the directory exists
if [ ! -d "$root_dir" ]; then
    echo "Error: Directory '$root_dir' does not exist"
    exit 1
fi

# Clear the output file
> "$output_file"

# Find all .py files and process them
find "$root_dir" -name "*.py" -type f | while read -r file; do
    echo "=== $file ===" >> "$output_file"
    cat "$file" >> "$output_file"
    echo "" >> "$output_file"
done

echo "All Python files from '$root_dir' combined into $output_file"