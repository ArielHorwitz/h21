FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/
COPY static/ static/
COPY daily-solutions.txt .
COPY config.toml .

EXPOSE 8000

CMD ["uvicorn", "h21.main:app", "--host", "0.0.0.0", "--port", "8000"]
