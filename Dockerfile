# FROM python:3.11-slim AS builder

# WORKDIR /app

# RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# COPY requirements.txt .
# RUN pip install --user --no-cache-dir -r requirements.txt

# FROM python:3.11-slim

# WORKDIR /app

# RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev && rm -rf /var/lib/apt/lists/*

# COPY --from=builder /root/.local /root/.local
# ENV PATH=/root/.local/bin:$PATH

# COPY app/ ./app/

# # Non-root user
# RUN useradd -m appuser && chown -R appuser /app
# USER appuser

# EXPOSE 8000

# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]




# =================================================================
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc python3-dev libffi-dev libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]