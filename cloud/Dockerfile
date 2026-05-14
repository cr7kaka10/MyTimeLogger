FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MYTIMELOGGER_CLOUD_MODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY cloud/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/cloud/data /app/cloud/attachments /app/reports /app/log

EXPOSE 8000

CMD ["uvicorn", "cloud.main:app", "--host", "0.0.0.0", "--port", "8000"]
