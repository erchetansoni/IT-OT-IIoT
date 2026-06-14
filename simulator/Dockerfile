FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir paho-mqtt>=2.1.0

COPY plc_simulator.py .

CMD ["python", "-u", "plc_simulator.py"]
