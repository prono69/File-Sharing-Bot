FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# We will NOT copy code here (important!)
# COPY . . ← remove or comment this line

CMD ["python", "main.py"]