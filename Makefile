# Makefile for Aeonisk document conversions

# Shell to use
SHELL := /bin/bash

# --- Configuration ---
PODMAN_IMAGE_NAME := yags-converter
PODMANFILE := Podmanfile

# Directories
CONTENT_DIR := content
RELEASES_DIR := releases

YAGS_CONVERT_SCRIPT := scripts/convert_yagsbook.sh
CONVERTED_YAGS_BASE_DIR := converted_yagsbook
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
.PHONY: test test-unit test-integration test-cov test-fast test-schemas test-mechanics
.PHONY: lint format format-check install-test-deps clean-test

# Default target
all: convert_markdown convert_yags

# Build the Podman image
build_podman_image:
	@echo "Building Podman image $(PODMAN_IMAGE_NAME)..."
	@podman build -f $(PODMANFILE) -t $(PODMAN_IMAGE_NAME) .

# Convert Markdown files from content/ directory
# This target implicitly depends on the image existing.
# We can make it explicit if we want `make convert_markdown` to also build the image.
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

# =============================================================================
# Testing Targets
# =============================================================================

# Run all tests
test:
	@echo "Running all tests..."
	@source .venv/bin/activate && cd scripts && python -m pytest ../tests/ -v

# Run unit tests only (fast, no LLM calls)
test-unit:
	@echo "Running unit tests..."
	@source .venv/bin/activate && cd scripts && python -m pytest ../tests/unit/ -v

# Run integration tests (may be slower)
test-integration:
	@echo "Running integration tests..."
	@source .venv/bin/activate && cd scripts && python -m pytest ../tests/integration/ -v --asyncio-mode=auto

# Run tests with coverage report
test-cov:
	@echo "Running tests with coverage..."
	@source .venv/bin/activate && cd scripts && \
		python -m pytest ../tests/ \
		--cov=aeonisk/multiagent \
		--cov-report=html \
		--cov-report=term \
		-v
	@echo ""
	@echo "Coverage report generated in scripts/aeonisk/htmlcov/index.html"

# Run tests with minimal output (for CI or quick checks)
test-fast:
	@echo "Running tests (fast mode)..."
	@source .venv/bin/activate && cd scripts && python -m pytest ../tests/ -q

# Run specific test suites
test-schemas:
	@echo "Running schema validation tests..."
	@source .venv/bin/activate && cd scripts && python -m pytest ../tests/unit/test_schemas.py -v

test-mechanics:
	@echo "Running mechanics tests..."
	@source .venv/bin/activate && cd scripts && python -m pytest ../tests/unit/test_mechanics.py -v

# =============================================================================
# Code Quality Targets
# =============================================================================

# Run linter
lint:
	@echo "Running flake8 linter..."
	@source .venv/bin/activate && cd scripts && \
		flake8 aeonisk/multiagent/ \
		--max-line-length=120 \
		--exclude=__pycache__,.venv \
		--ignore=E203,W503
	@echo "Linting complete!"

# Format code
format:
	@echo "Formatting code with black..."
	@source .venv/bin/activate && cd scripts && \
		black aeonisk/multiagent/ --line-length=120
	@echo "Sorting imports with isort..."
	@source .venv/bin/activate && cd scripts && \
		isort aeonisk/multiagent/ --profile=black
	@echo "Formatting complete!"

# Check formatting without making changes
format-check:
	@echo "Checking code formatting..."
	@source .venv/bin/activate && cd scripts && \
		black aeonisk/multiagent/ --check --line-length=120
	@source .venv/bin/activate && cd scripts && \
		isort aeonisk/multiagent/ --check-only --profile=black
	@echo "Format check complete!"

# =============================================================================
# Setup and Maintenance
# =============================================================================

# Install test dependencies
install-test-deps:
	@echo "Installing test dependencies..."
	@source .venv/bin/activate && \
		pip install -r scripts/aeonisk/requirements-dev.txt
	@echo "Test dependencies installed!"

# Clean up test artifacts
clean-test:
	@echo "Cleaning test artifacts..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf scripts/aeonisk/htmlcov 2>/dev/null || true
	@rm -rf scripts/aeonisk/.coverage 2>/dev/null || true
	@echo "Test cleanup complete!"

# =============================================================================
# Help
# =============================================================================

# Help target
help:
	@echo "Aeonisk YAGS - Available Commands"
	@echo ""
	@echo "Document Conversion:"
	@echo "  all                - Build image (if needed) and run all conversions"
	@echo "  build_podman_image - Build the Podman image '$(PODMAN_IMAGE_NAME)'"
	@echo "  convert_markdown   - Convert Markdown files from '$(CONTENT_DIR)/' to PDF/EPUB"
	@echo "  convert_yags       - Convert specified .yags files to Markdown/EPUB"
	@echo ""
	@echo "Testing:"
	@echo "  test               - Run all tests"
	@echo "  test-unit          - Run unit tests only (fast)"
	@echo "  test-integration   - Run integration tests (slower)"
	@echo "  test-cov           - Run tests with coverage report"
	@echo "  test-fast          - Run tests with minimal output"
	@echo "  test-schemas       - Run schema validation tests"
	@echo "  test-mechanics     - Run mechanics tests"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint               - Run flake8 linter"
	@echo "  format             - Format code with black and isort"
	@echo "  format-check       - Check formatting without changes"
	@echo ""
	@echo "Setup & Cleanup:"
	@echo "  install-test-deps  - Install testing dependencies"
	@echo "  clean              - Remove all generated document files"
	@echo "  clean-test         - Remove test artifacts"
	@echo "  clean_backups      - Clean up backup files created during conversion"
	@echo ""
	@echo "  help               - Show this help message"
