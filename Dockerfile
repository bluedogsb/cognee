# Use a Python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS uv

# Install the project into `/app`
WORKDIR /app

# Enable bytecode compilation
# ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Set build argument
ARG DEBUG

# Set environment variable based on the build argument
ENV DEBUG=${DEBUG}

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    git \
    curl \
    cmake \
    clang \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and lockfile first for better caching
COPY README.md pyproject.toml uv.lock entrypoint.sh ./

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --extra debug --extra api --extra postgres --extra neo4j --extra llama-index --extra ollama --extra mistral --extra groq --extra anthropic --extra chromadb --frozen --no-install-project --no-dev --no-editable

# Then, add the rest of the project source code and install it
# Installing separately from its dependencies allows optimal layer caching
COPY ./cognee /app/cognee
COPY ./distributed /app/distributed
# Compatibility shim that re-exports ladybug under the legacy `kuzu`
# module name. Listed in [tool.hatch.build.targets.wheel] packages, and
# imported at module load by alembic/versions/b9274c27a25a_kuzu_11_migration.py.
COPY ./kuzu /app/kuzu
RUN --mount=type=cache,target=/root/.cache/uv \
uv sync --extra debug --extra api --extra postgres --extra neo4j --extra llama-index --extra ollama --extra mistral --extra groq --extra anthropic --extra chromadb --frozen --no-dev --no-editable

# PLATFORM-PATCH (gamemagick 2026-05-24): pre-download wheels for the Kuzu
# graph DB migration that runs at container startup. The migration code at
# cognee/infrastructure/databases/graph/ladybug/ladybug_migrate.py:85-109
# creates a temp venv and does `pip install --upgrade pip` + `pip install
# kuzu==<old_version>` + `pip install ladybug==<new_version>` to bridge a
# version-format change. Cognee runtime containers in the gamemagick deploy
# have NO outbound internet (platform-egress firewall — by design), so the
# pip install fails with "Temporary failure in name resolution".
# Vendor wheels at image-build time (builder stage has internet); set
# PIP_FIND_LINKS + PIP_NO_INDEX in the runtime stage so the migration's
# subprocess pip calls find local wheels.
# See PLATFORM_PATCHES.md in fork root for upstream-sync note.
RUN mkdir -p /opt/cognee-migration-wheels && \
    pip download --dest /opt/cognee-migration-wheels \
        pip setuptools wheel \
        kuzu==0.11.3 \
        ladybug==0.16.0

FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=uv /app /app
# COPY --from=uv /app/.venv /app/.venv
# COPY --from=uv /root/.local /root/.local

# PLATFORM-PATCH (gamemagick 2026-05-24): copy pre-vendored Kuzu migration
# wheels from the builder stage. See PLATFORM_PATCHES.md for rationale.
COPY --from=uv /opt/cognee-migration-wheels /opt/cognee-migration-wheels

# Strip Windows carriage returns (fixes "no such file" on Windows Docker)
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

ENV PYTHONPATH=/app
# ENV LOG_LEVEL=ERROR
ENV PYTHONUNBUFFERED=1

# PLATFORM-PATCH (gamemagick 2026-05-24): point pip at vendored wheels and
# disable pypi index so the offline Kuzu migration succeeds. Affects ALL pip
# operations inside the container — acceptable because cognee runtime should
# not need to fetch anything from the network at runtime. See
# PLATFORM_PATCHES.md for full rationale.
ENV PIP_FIND_LINKS=/opt/cognee-migration-wheels
ENV PIP_NO_INDEX=1

ENTRYPOINT ["/app/entrypoint.sh"]
