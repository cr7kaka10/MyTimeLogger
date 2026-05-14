FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MYTIMELOGGER_CLOUD_MODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY . .

RUN mkdir -p /app/cloud_data /app/cloud_attachments /app/reports /app/log

EXPOSE 8000

CMD ["uvicorn", "cloud_sleep_api:app", "--host", "0.0.0.0", "--port", "8000"]
