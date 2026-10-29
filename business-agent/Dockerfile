FROM python:3.13-slim

# ffmpeg — извлечение кадров из видео, GIF и видеостикеров
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home agent && mkdir -p /app/storage && chown agent /app/storage
USER agent

CMD ["python", "-m", "app.main"]
