FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY xauusd_bot_final.py .

CMD ["python", "xauusd_bot_final.py"]
