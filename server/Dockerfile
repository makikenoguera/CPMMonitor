FROM python:3.11-slim

WORKDIR /app

# gcc para numpy; libchromaprint1 para decodificación nativa de fingerprints
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libchromaprint1 \
    && rm -rf /var/lib/apt/lists/*

# Dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código
COPY main.py .

EXPOSE 8300
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8300", "--workers", "2"]
