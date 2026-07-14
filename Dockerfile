FROM python:3.12-slim

# libgl1/libglib2.0-0: required by opencv-python-headless (a docling-ibm-models
# transitive dep) at import time, not just build time.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY schemas ./schemas
COPY observability ./observability
COPY pipeline ./pipeline
COPY statute_kb ./statute_kb
COPY db ./db

# CPU-only torch+torchvision first, installed together so their ABIs match —
# the default PyPI wheels also pull ~2GB of unused NVIDIA CUDA packages,
# which this container never uses.
RUN pip install --no-cache-dir torch==2.13.0 torchvision==0.28.0 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -e .

COPY . .

CMD ["python", "-m", "pipeline.run", "--help"]
