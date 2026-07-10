FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Hugging Face Spaces (Docker SDK) espera el servicio en el puerto 7860.
# Directorios de cache con permisos de escritura (necesario para el modelo de rembg).
ENV HOME=/app \
    U2NET_HOME=/app/.u2net \
    XDG_CACHE_HOME=/app/.cache
RUN mkdir -p /app/.u2net /app/.cache && chmod -R 777 /app

EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
