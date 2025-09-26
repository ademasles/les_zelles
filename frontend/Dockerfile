# Dockerfile for the Analyse DCE Frontend
# This Dockerfile sets up a Python environment with necessary dependencies for the frontend service.

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 3000

CMD ["streamlit", "run", "app.py", "--server.port=3000", "--server.address=0.0.0.0"]
