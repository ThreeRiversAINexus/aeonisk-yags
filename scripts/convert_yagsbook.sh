#!/usr/bin/env bash
# YAGS book conversion script
# Converts YAGS DocBook (.yags) files to Markdown and EPUB formats
# Usage: ./convert_yagsbook.sh /path/to/yags_file.yags

set -e

# Check if a file path was provided
if [ $# -eq 0 ]; then
  echo "Error: No input file specified."
  echo "Usage: $0 /path/to/yags_file.yags"
  exit 1
fi

# Parse command line arguments
INPUT_FILE="$1"
BASE_NAME=$(basename "$INPUT_FILE" .yags)

# Set up directory paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(pwd)"
ARCHIVE_ROOT="${ARCHIVE_ROOT:-$PROJECT_ROOT/archive}"
TEMP_DIR="$PROJECT_ROOT/temp_docbook_processing"
MARKDOWN_OUTPUT_DIR="$ARCHIVE_ROOT/converted_yagsbook/markdown"
EPUB_OUTPUT_DIR="$ARCHIVE_ROOT/converted_yagsbook/epub"

# Create necessary directories
mkdir -p "$TEMP_DIR"
mkdir -p "$MARKDOWN_OUTPUT_DIR"
mkdir -p "$EPUB_OUTPUT_DIR"

# Copy input file to temp directory
cp "$INPUT_FILE" "$TEMP_DIR/$BASE_NAME.yags"
echo "Copied input file to temporary directory: $TEMP_DIR/$BASE_NAME.yags"

# Set up paths for container volumes
HOST_INPUT_DIR="$PROJECT_ROOT/temp_docbook_processing"
HOST_OUTPUT_MARKDOWN_DIR="$ARCHIVE_ROOT/converted_yagsbook/markdown"
HOST_OUTPUT_EPUB_DIR="$ARCHIVE_ROOT/converted_yagsbook/epub"

# Display information
echo "Input YAGS file (host): $INPUT_FILE"
echo "Output Markdown dir (host): $HOST_OUTPUT_MARKDOWN_DIR"
echo "Output EPUB dir (host):     $HOST_OUTPUT_EPUB_DIR"

# Run the conversion in a Podman container
echo "Starting Podman container for conversion..."
podman run --rm \
  -v "$HOST_INPUT_DIR:/app/docbook_input:Z" \
  -v "$HOST_OUTPUT_MARKDOWN_DIR:/app/output_markdown:Z" \
  -v "$HOST_OUTPUT_EPUB_DIR:/app/output_epub:Z" \
  -v "$SCRIPT_DIR:/app/scripts:Z" \
  -e DOCBOOK_INPUT_FILE="/app/docbook_input/$BASE_NAME.yags" \
  -e DOCBOOK_OUTPUT_DIR_MD="/app/output_markdown" \
  -e DOCBOOK_OUTPUT_DIR_EPUB="/app/output_epub" \
  yags-converter \
  /usr/local/bin/internal_podman_convert.sh

# Run table fixing scripts in sequence
echo "Applying table fixes to $MARKDOWN_OUTPUT_DIR/$BASE_NAME.md..."
python3 "$SCRIPT_DIR/table_fixes/direct_table_fix.py" "$MARKDOWN_OUTPUT_DIR/$BASE_NAME.md"
python3 "$SCRIPT_DIR/table_fixes/final_fixes.py" "$MARKDOWN_OUTPUT_DIR/$BASE_NAME.md"
python3 "$SCRIPT_DIR/table_fixes/fix_duplicates.py" "$MARKDOWN_OUTPUT_DIR/$BASE_NAME.md"
python3 "$SCRIPT_DIR/table_fixes/fix_table_formatting.py" "$MARKDOWN_OUTPUT_DIR/$BASE_NAME.md"

# Clean up
echo "Cleaning up temporary input directory."
rm -rf "$TEMP_DIR"

echo "Conversion process finished."
echo "Output files:"
echo "  Markdown: $MARKDOWN_OUTPUT_DIR/$BASE_NAME.md"
echo "  EPUB: $EPUB_OUTPUT_DIR/$BASE_NAME.epub"
