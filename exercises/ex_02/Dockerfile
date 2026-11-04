FROM python:3.12-slim
RUN pip install --no-cache-dir "paho-mqtt>=2.1,<3"
COPY rhythms.py index.html /app/
CMD ["python3", "-u", "/app/rhythms.py"]
