ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

RUN if ! command -v tc >/dev/null 2>&1; then \
        apt-get update \
        && apt-get install -y --no-install-recommends iproute2 iputils-ping \
        && rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /work
ENV PYTHONPATH=/work
ENTRYPOINT []
