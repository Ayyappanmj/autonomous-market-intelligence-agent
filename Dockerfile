FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN useradd -m appuser && mkdir -p /app/data && chown -R appuser /app
USER appuser
ENV PORT=8000 MODE=gateway DATABASE_PATH=/app/data/market_intel.db
EXPOSE 8000
CMD ["python", "start.py"]
