FROM python:3.12-alpine
# ping forces the ARP exchange, ip reads the neighbour table
RUN apk add --no-cache iputils-ping iproute2 \
 && pip install --no-cache-dir "paho-mqtt>=2.1,<3"
COPY presence.py /presence.py
CMD ["python3", "-u", "/presence.py"]
