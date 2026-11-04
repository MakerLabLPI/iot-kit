# Debian-based on purpose: the Pi 5 NeoPixel driver ships a glibc arm64 wheel
FROM python:3.12-slim
RUN pip install --no-cache-dir "paho-mqtt>=2.1,<3" Adafruit-Blinka-Raspberry-Pi5-Neopixel
COPY leds.py /leds.py
CMD ["python3", "-u", "/leds.py"]
