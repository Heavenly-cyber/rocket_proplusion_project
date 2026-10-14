ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE} AS compiler
ARG LLAMA_COMMIT
COPY docker/debian.sources /etc/apt/sources.list.d/debian.sources
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git cmake build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /source
RUN test "${#LLAMA_COMMIT}" = 40 \
    && git init \
    && git remote add origin https://github.com/ggml-org/llama.cpp.git \
    && git fetch --depth 1 origin "${LLAMA_COMMIT}" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "${LLAMA_COMMIT}" \
    && cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
       -DGGML_NATIVE=OFF -DGGML_BACKEND_DL=ON -DGGML_CPU_ALL_VARIANTS=ON \
       -DBUILD_SHARED_LIBS=ON -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF \
       -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=ON -DGGML_CUDA=OFF \
    && cmake --build build --target llama-server --parallel 2 \
    && printf '%s\n' "$LLAMA_COMMIT" > build/bin/SOURCE_COMMIT \
    && dpkg-query -W > build/bin/COMPILER_PACKAGES.txt
FROM ${PYTHON_IMAGE}
COPY docker/debian.sources /etc/apt/sources.list.d/debian.sources
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && dpkg-query -W > /RUNTIME_PACKAGES.txt \
    && rm -rf /var/lib/apt/lists/*
COPY --from=compiler /source/build/bin/ /opt/llama/
ENV LD_LIBRARY_PATH=/opt/llama GGML_BACKEND_DIR=/opt/llama HOME=/tmp/home
USER 65532:65532
ENTRYPOINT ["/opt/llama/llama-server"]
