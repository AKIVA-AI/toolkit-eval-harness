FROM python:3.11-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir build && python -m build --wheel

FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

RUN mkdir -p /app/packs /app/results /app/suites

ENV PYTHONUNBUFFERED=1
ENV EVAL_HARNESS_HOME=/app

CMD ["toolkit-eval", "--help"]
