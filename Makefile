# Controlling Cockpit – pipeline commands (macOS / Linux, GNU make)
# Run `make help` for an overview.

PYTHON ?= python3
VENV   := .venv
PY     := $(VENV)/bin/python
PIP    := $(VENV)/bin/pip

.DEFAULT_GOAL := help
.PHONY: help setup data build quality analysis excel powerbi all test lint format clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## Create the virtual environment and install dependencies
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -r requirements.txt
	$(PIP) install --quiet -e .
	@echo "Environment ready: $(VENV)"

data: ## Generate synthetic raw data (data/raw/, fixed seed)
	$(PY) -m cockpit.generate_data

build: ## Build DuckDB warehouse (staging -> DQ -> star schema), export data/model/, render PBIP
	$(PY) -m cockpit.warehouse build
	$(PY) -m cockpit.powerbi_model

quality: ## Print the data-quality report (fails if reconciliation fails)
	$(PY) -m cockpit.warehouse quality

analysis: ## Print the analytical SQL views (04_analysis.sql)
	$(PY) -m cockpit.warehouse analysis

excel: ## Build excel/controlling_reconciliation.xlsx
	$(PY) -m cockpit.excel_workbook

powerbi: ## Re-render the Power BI project (TMDL, PBIR scaffold, measures.dax)
	$(PY) -m cockpit.powerbi_model

all: data build quality excel ## Run the full pipeline end to end

test: ## Run the test suite
	$(PY) -m pytest

lint: ## Lint with ruff
	$(VENV)/bin/ruff check src tests

format: ## Auto-fix lint issues and format with ruff
	$(VENV)/bin/ruff check --fix src tests
	$(VENV)/bin/ruff format src tests

clean: ## Remove generated warehouse and caches (keeps committed sample data)
	rm -f data/warehouse.duckdb data/warehouse.duckdb.wal
	rm -rf .pytest_cache .ruff_cache src/*.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
