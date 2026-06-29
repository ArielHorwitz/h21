FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/
COPY static/ static/

ENV XDG_CONFIG_HOME=/app/config
ENV XDG_DATA_HOME=/app/data

RUN mkdir -p /app/config/h21 /app/data/h21

EXPOSE 8000

CMD ["uvicorn", "h21.main:app", "--host", "0.0.0.0", "--port", "8000"]
