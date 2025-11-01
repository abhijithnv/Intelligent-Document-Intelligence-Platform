# ===============================
# Base Image
# ===============================
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev gcc git \
    && rm -rf /var/lib/apt/lists/*

# ===============================
# Copy and Install Dependencies
# ===============================
COPY requirements.txt .

# Use CPU-only PyTorch (lighter build, avoids CUDA download)
# Install torch>=2.6.0 required by transformers due to security fix (CVE-2025-32434)
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    torch>=2.6.0 torchvision>=0.21.0 torchaudio>=2.6.0 && \
    pip install --no-cache-dir -r requirements.txt

# ===============================
# Copy Application Code
# ===============================
COPY . .

# Expose port
EXPOSE 8000

# ===============================
# Start FastAPI App
# ===============================
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
