FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FATURA_DATA_DIR=/data \
    FATURA_SERVER_HOST=0.0.0.0 \
    FATURA_SERVER_PORT=8080

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./
RUN mkdir -p /data

EXPOSE 8080
CMD ["python", "run_server.py"]
