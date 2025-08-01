.PHONY: checks
checks:  ruff mypy

.PHONY: ruff
ruff:
	@if command -v uv >/dev/null 2>&1; then \
		uv run ruff check able_assistant data_assistant hypothesis_assistant planning_assistant research_assistant UI utils peak_mcp; \
	else \
		ruff check able_assistant data_assistant hypothesis_assistant planning_assistant research_assistant UI utils peak_mcp; \
	fi

.PHONY: mypy
mypy:
	@if command -v uv >/dev/null 2>&1; then \
		uv run mypy able_assistant data_assistant hypothesis_assistant planning_assistant research_assistant UI utils peak_mcp; \
	else \
		mypy able_assistant data_assistant hypothesis_assistant planning_assistant research_assistant UI utils peak_mcp; \
	fi

.PHONY: coverage
coverage:
	@if command -v uv >/dev/null 2>&1; then \
		uv run coverage run -m pytest; \
	else \
		coverage run -m pytest; \
	fi
.PHONY: coverage-report
coverage-report:
	@if command -v uv >/dev/null 2>&1; then \
		uv run coverage report; \
	else \
		coverage report; \
	fi

.PHONY: coverage-html
coverage-html:

	@if command -v uv >/dev/null 2>&1; then \
		uv run coverage html; \
	else \
		coverage html; \
	fi	