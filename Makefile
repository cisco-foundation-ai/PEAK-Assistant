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

.PHONY: container-local
container-local:
	docker buildx build -t ghcr.io/splunk/peak-assistant:$(shell git branch --show-current) --load .


.PHONY: container-run
container-run: container-local
	docker run --rm -it \
		--mount "type=bind,src=$(PWD),target=/certs" \
		--mount "type=bind,src=$(PWD)/context.txt,target=/home/peakassistant/context.txt" \
		-p "127.0.0.1:8000:8000" \
		ghcr.io/splunk/peak-assistant:$(shell git branch --show-current)