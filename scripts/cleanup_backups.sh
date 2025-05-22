#!/bin/bash
# Script to clean up backup files created during conversion

echo "Cleaning up backup files..."

# Find and remove all .bak* files in the converted_yagsbook directory
find ./converted_yagsbook -type f -name "*.bak*" -exec rm -f {} \;
echo "Removed .bak files from converted_yagsbook/"

# Find and remove any temporary files
find ./converted_yagsbook -type f -name "*.tmp" -exec rm -f {} \;
echo "Removed .tmp files from converted_yagsbook/"

# Find and remove old versions that might have been kept
find ./converted_yagsbook -type f -name "*~" -exec rm -f {} \;
echo "Removed backup (~) files from converted_yagsbook/"

# Find and remove any .new files
find ./scripts -type f -name "*.new" -exec rm -f {} \;
echo "Removed .new files from scripts/"

# Clean the temp directory if it exists
if [ -d "./temp_docbook_processing" ]; then
    rm -rf ./temp_docbook_processing
    echo "Removed temp_docbook_processing directory"
fi

echo "Backup file cleanup complete!"
