ARG PYTHON_IMAGE
ARG UV_IMAGE
FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE}
COPY --from=uv /uv /uvx /usr/local/bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv UV_CACHE_DIR=/tmp/uv-cache \
    PATH=/opt/venv/bin:$PATH PYTHONPATH=/app/src MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib XDG_CACHE_HOME=/tmp/cache HOME=/tmp/home \
    OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-editable --group dev \
    && rm -rf /tmp/uv-cache
COPY src ./src
COPY tests ./tests
COPY scripts ./scripts
COPY configs/stack-selection.json configs/cpu-profile.json ./configs/
COPY docs/PROJECT_MANIFESTO.md ./docs/PROJECT_MANIFESTO.md
USER 65532:65532
ENTRYPOINT ["python", "-m", "rocket_nozzle_llm"]
