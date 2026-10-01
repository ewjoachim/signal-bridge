FROM python:3.14-slim@sha256:44dd04494ee8f3b538294360e7c4b3acb87c8268e4d0a4828a6500b1eff50061

COPY --from=ghcr.io/astral-sh/uv:0.11.24@sha256:99ea34acedc870ba4ad11a1f540a1c04267c9f30aadc465a94406f52dfda2c36 /uv /uvx /bin/

# The JVM build of signal-cli, not the native one: the native binary requires
# x86-64-v3 (AVX2), which the production server's Atom C2338 lacks.
COPY --from=eclipse-temurin:25-jre@sha256:8da0490fa9a3c26867012019565948eef0ee69438f5c75ac28146967bae984b5 /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk

# renovate: datasource=github-releases depName=AsamK/signal-cli
ARG SIGNAL_CLI_VERSION=0.14.8
ADD https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}.tar.gz /tmp/signal-cli.tar.gz
RUN mkdir /opt/signal-cli \
    && tar -xzf /tmp/signal-cli.tar.gz -C /opt/signal-cli --strip-components=1 \
    && ln -s /opt/signal-cli/bin/signal-cli /usr/local/bin/signal-cli \
    && rm /tmp/signal-cli.tar.gz

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_FROZEN=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

ARG BUILD_VERSION=0.0.0
COPY pyproject.toml README.md uv.lock ./
RUN UV_DYNAMIC_VERSIONING_BYPASS="$BUILD_VERSION" uv sync --no-default-groups --no-install-project

RUN groupadd -g 10001 app \
    && useradd -u 10001 -g 10001 -m app \
    && mkdir -p /data \
    && chown 10001:10001 /data

COPY . ./
RUN UV_DYNAMIC_VERSIONING_BYPASS="$BUILD_VERSION" uv sync --no-default-groups

USER 10001:10001

VOLUME /data

# The loop touches the heartbeat after each successful `signal-cli receive`.
# A failing check makes `podman auto-update` roll back to the previous image.
HEALTHCHECK --interval=1m --timeout=5s --start-period=2m --retries=3 \
    CMD python -c "import os, sys, time; sys.exit(time.time() - os.path.getmtime('/tmp/signal-bridge.heartbeat') > 900)"

CMD ["python", "-m", "signal_bridge"]
