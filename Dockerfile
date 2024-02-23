FROM nvidia/cuda:12.2.2-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt install -y --no-install-recommends \
        python3-pip espeak-ng libespeak-ng1 libclblast1 && \
    apt clean && rm -rf /var/lib/apt/lists/*
RUN pip --no-cache-dir install poetry

WORKDIR /app
COPY . .

RUN poetry install --no-interaction
RUN rm -rf ~/.cache/pypoetry/{cache,artifacts}

CMD ["poetry", "run", "oobabot"]
