#!/bin/bash

# Script to convert a .yags (DocBook XML) file to Markdown and EPUB using pandoc.

# --- Configuration ---
# Host paths (script assumes it's run from project root or `scripts/` dir)
# Adjust if script is run from a different CWD
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
PROJECT_ROOT=$(realpath "${SCRIPT_DIR}/..") # Assumes script is in scripts/

HOST_OUTPUT_BASE_DIR="${PROJECT_ROOT}/converted_yagsbook"
HOST_MARKDOWN_DIR="${HOST_OUTPUT_BASE_DIR}/markdown"
HOST_EPUB_DIR="${HOST_OUTPUT_BASE_DIR}/epub"
TEMP_INPUT_DIR_HOST="${PROJECT_ROOT}/temp_docbook_processing"

# Container paths
CONTAINER_INPUT_DIR="/app/docbook_input"
CONTAINER_MD_OUTPUT_DIR="/app/output_markdown"
CONTAINER_EPUB_OUTPUT_DIR="/app/output_epub"

PODMAN_IMAGE_NAME="yags-converter" # Should match the image built by Podmanfile

# --- Functions ---
function print_usage() {
    echo "Usage: $0 <path_to_yags_file>"
    echo "Converts a .yags (DocBook XML) file to Markdown and EPUB using a Podman container."
    echo "Example: $0 ../yags/src/core/core.yags  (if run from scripts/)"
    echo "Example: ./scripts/convert_yagsbook.sh yags/src/core/core.yags (if run from project root)"
}

function ensure_dir() {
    if [ ! -d "$1" ]; then
        mkdir -p "$1"
        echo "Created directory: $1"
    fi
}

# --- Main Script ---

# Check if input file is provided
if [ -z "$1" ]; then
    echo "Error: No input .yags file specified."
    print_usage
    exit 1
fi

INPUT_YAGS_FILE_HOST_PATH="$1"

# Ensure input file path is absolute or resolve it relative to current CWD
if [[ ! "$INPUT_YAGS_FILE_HOST_PATH" = /* ]]; then
  INPUT_YAGS_FILE_HOST_PATH="$(pwd)/${INPUT_YAGS_FILE_HOST_PATH}"
fi
INPUT_YAGS_FILE_HOST_PATH=$(realpath "$INPUT_YAGS_FILE_HOST_PATH")


# Check if input file exists
if [ ! -f "$INPUT_YAGS_FILE_HOST_PATH" ]; then
    echo "Error: Input file '${INPUT_YAGS_FILE_HOST_PATH}' not found."
    exit 1
fi

INPUT_YAGS_FILENAME=$(basename "$INPUT_YAGS_FILE_HOST_PATH")

# Prepare temporary input directory
ensure_dir "$TEMP_INPUT_DIR_HOST"
cp "$INPUT_YAGS_FILE_HOST_PATH" "${TEMP_INPUT_DIR_HOST}/${INPUT_YAGS_FILENAME}"
echo "Copied input file to temporary directory: ${TEMP_INPUT_DIR_HOST}/${INPUT_YAGS_FILENAME}"

# Ensure host output directories exist
ensure_dir "$HOST_MARKDOWN_DIR"
ensure_dir "$HOST_EPUB_DIR"

echo "Starting Podman container for conversion..."
echo "Input YAGS file (host): ${INPUT_YAGS_FILE_HOST_PATH}"
echo "Output Markdown dir (host): ${HOST_MARKDOWN_DIR}"
echo "Output EPUB dir (host):     ${HOST_EPUB_DIR}"

# Run the Podman container
podman run --rm \
    -v "${TEMP_INPUT_DIR_HOST}:${CONTAINER_INPUT_DIR}:ro,Z" \
    -v "${HOST_MARKDOWN_DIR}:${CONTAINER_MD_OUTPUT_DIR}:Z" \
    -v "${HOST_EPUB_DIR}:${CONTAINER_EPUB_OUTPUT_DIR}:Z" \
    -e "DOCBOOK_INPUT_FILE=${CONTAINER_INPUT_DIR}/${INPUT_YAGS_FILENAME}" \
    -e "DOCBOOK_OUTPUT_DIR_MD=${CONTAINER_MD_OUTPUT_DIR}" \
    -e "DOCBOOK_OUTPUT_DIR_EPUB=${CONTAINER_EPUB_OUTPUT_DIR}" \
    "${PODMAN_IMAGE_NAME}"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "Podman container finished successfully."
else
    echo "Error: Podman container exited with code $EXIT_CODE."
fi

# Clean up temporary input directory
rm -f "${TEMP_INPUT_DIR_HOST}/${INPUT_YAGS_FILENAME}"
rmdir "$TEMP_INPUT_DIR_HOST" # rmdir only removes empty directories
echo "Cleaned up temporary input directory."

echo "Conversion process finished."
exit $EXIT_CODE
