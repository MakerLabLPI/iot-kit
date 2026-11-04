# One static page, served by Python's http.server (the same base image as
# the exercises, so nothing new to pull on the Pi).
FROM python:3.12-slim
COPY index.html /app/
WORKDIR /app
CMD ["python3", "-u", "-m", "http.server", "8000", "--bind", "0.0.0.0"]
