FROM python:3.14-slim-bookworm AS builder

WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.5
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY migrations ./migrations
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.14-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --system --gid 10001 sem \
    && useradd --system --uid 10001 --gid sem --home-dir /app --shell /usr/sbin/nologin sem
COPY --from=builder --chown=sem:sem /app/.venv /app/.venv
USER 10001:10001
EXPOSE 8000
CMD ["sem-api"]
