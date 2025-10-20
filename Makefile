# Makefile for Aeonisk document conversions

# Shell to use
SHELL := /bin/bash

# --- Configuration ---
PODMAN_IMAGE_NAME := yags-converter
PODMANFILE := Podmanfile

# Directories
CONTENT_DIR ?= archive/rulebooks
RELEASES_DIR ?= archive/releases

YAGS_CONVERT_SCRIPT := scripts/convert_yagsbook.sh
CONVERTED_YAGS_BASE_DIR ?= archive/converted_yagsbook
CONVERTED_YAGS_MD_DIR := $(CONVERTED_YAGS_BASE_DIR)/markdown
CONVERTED_YAGS_EPUB_DIR := $(CONVERTED_YAGS_BASE_DIR)/epub

# List of .yags files to convert
# Note: Paths are relative to the project root
YAGS_FILES_TO_CONVERT := \
    yags/src/core/core.yags \
    yags/src/core/combat.yags \
    yags/src/core/character.yags \
    yags/src/equipment/hightech.yags \
    yags/src/equipment/scifitech.yags \
    yags/src/bestiary/bestiary.yags

# Generate target names for .yags file outputs
YAGS_MD_TARGETS := $(patsubst yags/src/%.yags,$(CONVERTED_YAGS_MD_DIR)/%.md,$(filter yags/src/%.yags,$(YAGS_FILES_TO_CONVERT)))
YAGS_MD_TARGETS += $(patsubst yags/src/core/%.yags,$(CONVERTED_YAGS_MD_DIR)/%.md,$(filter yags/src/core/%.yags,$(YAGS_FILES_TO_CONVERT)))
YAGS_MD_TARGETS += $(patsubst yags/src/equipment/%.yags,$(CONVERTED_YAGS_MD_DIR)/%.md,$(filter yags/src/equipment/%.yags,$(YAGS_FILES_TO_CONVERT)))
YAGS_MD_TARGETS += $(patsubst yags/src/bestiary/%.yags,$(CONVERTED_YAGS_MD_DIR)/%.md,$(filter yags/src/bestiary/%.yags,$(YAGS_FILES_TO_CONVERT)))
YAGS_MD_TARGETS := $(sort $(YAGS_MD_TARGETS)) # Deduplicate and sort

YAGS_EPUB_TARGETS := $(patsubst %.md,%.epub,$(YAGS_MD_TARGETS))


# --- Targets ---

.PHONY: all build_podman_image convert_markdown convert_yags clean clean_backups help

# Default target
all: convert_markdown convert_yags

# Build the Podman image
build_podman_image:
	@echo "Building Podman image $(PODMAN_IMAGE_NAME)..."
	@podman build -f $(PODMANFILE) -t $(PODMAN_IMAGE_NAME) .

# Convert Markdown files from $(CONTENT_DIR)/
# This target implicitly depends on the image existing.
# Provide your own Markdown corpus in $(CONTENT_DIR)/ before invoking.
convert_markdown: build_podman_image
	@echo "Converting Markdown files from $(CONTENT_DIR)/ to PDF/EPUB in $(RELEASES_DIR)/..."
	@mkdir -p $(RELEASES_DIR)
	@podman run --rm \
		-v ./$(CONTENT_DIR):/app/content:ro,Z \
		-v ./$(RELEASES_DIR):/app/releases:Z \
		$(PODMAN_IMAGE_NAME)
	@echo "Markdown conversion finished. Outputs in $(RELEASES_DIR)/"

# Convert specified .yags files
convert_yags: build_podman_image $(YAGS_CONVERT_SCRIPT)
	@echo "Converting specified .yags files to Markdown/EPUB in $(CONVERTED_YAGS_BASE_DIR)/..."
	@for yags_file in $(YAGS_FILES_TO_CONVERT); do \
		echo "Processing $$yags_file..."; \
		./$(YAGS_CONVERT_SCRIPT) $$yags_file; \
	done
	@echo ".yags conversion finished. Outputs in $(CONVERTED_YAGS_BASE_DIR)/"

# Clean up generated files
clean:
	@echo "Cleaning up generated files..."
	@rm -rf $(RELEASES_DIR)
	@rm -rf $(CONVERTED_YAGS_BASE_DIR)
	@rm -f scripts/convert_yagsbook.log # remove log file if it exists
	@rm -rf temp_docbook_processing # remove temp dir from yags script
	@echo "Cleanup complete."

# Clean up backup files
clean_backups:
	@echo "Cleaning up backup files..."
	@./scripts/cleanup_backups.sh
	@echo "Backup cleanup complete."

# Help target
help:
	@echo "Available targets:"
	@echo "  all                - Build image (if needed) and run all conversions."
	@echo "  build_podman_image - Build the Podman image '$(PODMAN_IMAGE_NAME)'."
	@echo "  convert_markdown   - Convert Markdown files from '$(CONTENT_DIR)/' to PDF/EPUB."
	@echo "  convert_yags       - Convert specified .yags files to Markdown/EPUB."
	@echo "  clean              - Remove all generated files and directories."
	@echo "  clean_backups      - Clean up backup files created during conversion."
	@echo "  help               - Show this help message."
