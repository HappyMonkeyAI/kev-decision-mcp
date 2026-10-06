FROM python:3.13-slim@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake libgomp1 && rm -rf /var/lib/apt/lists/*
ENV CMAKE_ARGS="-DGGML_NATIVE=OFF -DGGML_CUDA=OFF" CMAKE_BUILD_PARALLEL_LEVEL=2
RUN pip install --no-cache-dir numpy==2.4.2 llama-cpp-python==0.3.36 --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
COPY .cache/gutsy/runtime /app/runtime
RUN pip install --no-cache-dir --no-deps /app/runtime
COPY integrations/gutsy/models.json /app/models.json
WORKDIR /app
USER 10001:10001
CMD ["gutsy-inference", "serve", "--config", "/app/models.json", "--host", "0.0.0.0", "--port", "8009", "--threads", "4", "--quiet"]
