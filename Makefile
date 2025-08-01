.PHONY: checks
checks:  ruff mypy

.PHONY: ruff
ruff:
	@if command -v uv >/dev/null 2>&1; then \
		uv run ruff check .; \
	else \
		ruff check .; \
	fi

.PHONY: mypy
mypy:
	@if command -v uv >/dev/null 2>&1; then \
		uv run mypy .; \
	else \
		mypy .; \
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
coverage-html: coverage

	@if command -v uv >/dev/null 2>&1; then \
		uv run coverage html; \
	else \
		coverage html; \
	fi	
	open htmlcov/index.html || echo "Open htmlcov/index.html in your browser to view the coverage report."