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