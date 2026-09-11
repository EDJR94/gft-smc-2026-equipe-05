FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the Chroma embedding model so container startup is instant
RUN python -c "import chromadb; client = chromadb.Client(); col = client.get_or_create_collection('warmup'); col.add(ids=['1'], documents=['warmup'])"

# Copy application source
COPY . .

EXPOSE 8080

# Default entrypoint runs the backend FastAPI app
CMD ["python", "-m", "src.api.main"]
