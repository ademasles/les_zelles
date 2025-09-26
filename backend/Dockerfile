# Dockerfile for the Analyse DCE Backend
# This Dockerfile sets up a Python environment with necessary dependencies for the backend service.

FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y python3.11 python3.11-venv python3-pip build-essential \
    git cmake libtesseract-dev tesseract-ocr tesseract-ocr-fra \
    poppler-utils curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN python3.11 -m pip install --upgrade pip && \
    python3.11 -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 && \
    python3.11 -m pip install -r requirements.txt

COPY . /app

RUN find /usr/local/lib/python3.11 -type d -name __pycache__ -exec rm -r {} + \
 && find /app -name '*.pyc' -delete

EXPOSE 8000

HEALTHCHECK CMD curl --fail http://localhost:8000/ping || exit 1

CMD ["python3.11", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
