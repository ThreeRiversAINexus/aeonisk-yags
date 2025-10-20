#!/bin/sh
set -e # Exit immediately if a command exits with a non-zero status.

echo "--- Starting conversion process in container ---"

if [ -n "$DOCBOOK_INPUT_FILE" ] && [ -f "$DOCBOOK_INPUT_FILE" ]; then
    # Mode 1: Convert a single DocBook file (passed via env var)
    # Assumes DOCBOOK_OUTPUT_DIR_MD and DOCBOOK_OUTPUT_DIR_EPUB are set and mounted.
    echo "DocBook conversion mode selected."
    echo "Input DocBook file: $DOCBOOK_INPUT_FILE"

    BASE_NAME=$(basename "${DOCBOOK_INPUT_FILE%.yags}") # Assuming .yags extension for DocBook

    MARKDOWN_OUTPUT_FILE="${DOCBOOK_OUTPUT_DIR_MD}/${BASE_NAME}.md"
    EPUB_OUTPUT_FILE="${DOCBOOK_OUTPUT_DIR_EPUB}/${BASE_NAME}.epub"

    echo "Outputting to Markdown: ${MARKDOWN_OUTPUT_FILE}"
    echo "Outputting to EPUB: ${EPUB_OUTPUT_FILE}"

    # Ensure output directories exist (relative to container's /app)
    mkdir -p "$DOCBOOK_OUTPUT_DIR_MD"
    mkdir -p "$DOCBOOK_OUTPUT_DIR_EPUB"

    # Convert to Markdown first using Pandoc with our improved filter
    if pandoc -f docbook -s --lua-filter=/app/pandoc/filters/yags_tables.lua "$DOCBOOK_INPUT_FILE" -o "$MARKDOWN_OUTPUT_FILE"; then
        echo "Successfully converted DocBook to Markdown: ${MARKDOWN_OUTPUT_FILE}"
    else
        echo "ERROR: Failed to convert DocBook to Markdown for ${DOCBOOK_INPUT_FILE}"
    fi

    # Convert to EPUB (from DocBook source or from the processed Markdown)
    if [ -f "$MARKDOWN_OUTPUT_FILE" ]; then
        if pandoc -f markdown -s "$MARKDOWN_OUTPUT_FILE" -o "$EPUB_OUTPUT_FILE"; then
            echo "Successfully converted Markdown to EPUB: ${EPUB_OUTPUT_FILE}"
        else
            echo "ERROR: Failed to convert Markdown to EPUB"
        fi
    else
        if pandoc -f docbook -s --lua-filter=/app/pandoc/filters/yags_tables.lua "$DOCBOOK_INPUT_FILE" -o "$EPUB_OUTPUT_FILE"; then
            echo "Successfully converted DocBook to EPUB: ${EPUB_OUTPUT_FILE}"
        else
            echo "ERROR: Failed to convert DocBook to EPUB for ${DOCBOOK_INPUT_FILE}"
        fi
    fi
else
    # Mode 2: Process Markdown files from /app/content (original functionality)
    echo "Markdown batch conversion mode selected."
    # Ensure the target directory exists (though Podmanfile's RUN should have made it)
    mkdir -p /app/releases

    # Find markdown files in /app/content and process them
    find /app/content -type f -name "*.md" -print0 | while IFS= read -r -d $'\0' FILE_PATH; do
        BASE_NAME=$(basename "${FILE_PATH%.md}")

        echo "Processing Markdown input file: ${FILE_PATH}"
        echo "Outputting to PDF: /app/releases/${BASE_NAME}.pdf"
        echo "Outputting to EPUB: /app/releases/${BASE_NAME}.epub"

        # Convert to PDF
        if pandoc --pdf-engine=xelatex "${FILE_PATH}" -o "/app/releases/${BASE_NAME}.pdf"; then
            echo "Successfully created PDF: /app/releases/${BASE_NAME}.pdf"
        else
            echo "ERROR: Failed to create PDF for ${FILE_PATH}"
        fi

        # Convert to EPUB
        if pandoc "${FILE_PATH}" -o "/app/releases/${BASE_NAME}.epub"; then
            echo "Successfully created EPUB: /app/releases/${BASE_NAME}.epub"
        else
            echo "ERROR: Failed to create EPUB for ${FILE_PATH}"
        fi
    done
fi

echo "--- Conversion process finished ---"
