# Game master for the Traitor's Game. Multi-arch base image: the same
# Dockerfile builds on the Pi 5 (arm64) and on a laptop.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY gamemaster/ gamemaster/
EXPOSE 8003
CMD ["python3", "-u", "-m", "gamemaster"]
