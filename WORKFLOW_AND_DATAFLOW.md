# IIoT Factory Monitoring — Workflow & Dataflow Documentation

> **Project**: Avgol IIoT Factory Monitoring System  
> **Version**: 1.0  
> **Last Updated**: 2026-06-14  

---

## Table of Contents

- [1. System Overview](#1-system-overview)
- [2. High-Level Architecture](#2-high-level-architecture)
- [3. Data Pipeline — End-to-End Flow](#3-data-pipeline--end-to-end-flow)
- [4. Component Deep-Dives](#4-component-deep-dives)
  - [4.1 PLC Simulator (Data Source)](#41-plc-simulator-data-source)
  - [4.2 Eclipse Mosquitto (MQTT Broker)](#42-eclipse-mosquitto-mqtt-broker)
  - [4.3 Telegraf (Metrics Bridge)](#43-telegraf-metrics-bridge)
  - [4.4 Prometheus (Time-Series Database)](#44-prometheus-time-series-database)
  - [4.5 Grafana (Visualization)](#45-grafana-visualization)
- [5. Data Formats & Transformations](#5-data-formats--transformations)
- [6. Network Topology & Port Map](#6-network-topology--port-map)
- [7. Docker Orchestration](#7-docker-orchestration)
- [8. Grafana Dashboard Specification](#8-grafana-dashboard-specification)
- [9. Sequence Diagram — Complete Data Journey](#9-sequence-diagram--complete-data-journey)
- [10. Configuration Reference](#10-configuration-reference)
- [11. Operational Runbook](#11-operational-runbook)
- [12. Troubleshooting Guide](#12-troubleshooting-guide)
- [13. Glossary](#13-glossary)

---

## 1. System Overview

This project implements a **full-stack Industrial IoT (IIoT) monitoring pipeline** using a containerized microservices architecture. It simulates a factory PLC (Programmable Logic Controller) generating real-time sensor telemetry, routes it through an MQTT message broker, transforms and exposes the data as Prometheus-compatible metrics, stores them in a time-series database, and visualizes everything on a live Grafana dashboard.

### Key Objectives

| Objective | Description |
|-----------|-------------|
| **Real-Time Monitoring** | Live factory sensor data displayed on dashboards with 5-second refresh |
| **Protocol Translation** | Convert MQTT pub/sub telemetry into Prometheus pull-based metrics |
| **Zero-Config Deployment** | Single `docker compose up` brings the entire stack online |
| **Extensibility** | Architecture supports adding real PLCs, additional sensors, and alerting |

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DOCKER COMPOSE NETWORK                               │
│                                                                             │
│  ┌──────────────┐    MQTT Publish     ┌──────────────┐                      │
│  │              │  ───────────────►   │              │                      │
│  │  PLC         │  Topic:             │  Mosquitto   │                      │
│  │  Simulator   │  factory/plc1       │  (MQTT       │                      │
│  │  (Python)    │  Port: N/A          │   Broker)    │                      │
│  │              │                     │  Port: 1883  │                      │
│  └──────────────┘                     └──────┬───────┘                      │
│                                              │                              │
│                                    MQTT Subscribe                           │
│                                    Topic: factory/plc1                      │
│                                              │                              │
│                                              ▼                              │
│                                      ┌──────────────┐                      │
│                                      │              │                      │
│                                      │  Telegraf    │                      │
│                                      │  (Metrics    │                      │
│                                      │   Bridge)    │                      │
│                                      │  Port: 9273  │                      │
│                                      └──────┬───────┘                      │
│                                              │                              │
│                                    HTTP Scrape (GET)                        │
│                                    /metrics endpoint                        │
│                                              │                              │
│                                              ▼                              │
│                                      ┌──────────────┐                      │
│                                      │              │                      │
│                                      │  Prometheus  │                      │
│                                      │  (TSDB)      │                      │
│                                      │  Port: 9090  │                      │
│                                      └──────┬───────┘                      │
│                                              │                              │
│                                    PromQL Queries                           │
│                                              │                              │
│                                              ▼                              │
│                                      ┌──────────────┐                      │
│                                      │              │                      │
│                                      │  Grafana     │                      │
│                                      │  (Dashboard) │                      │
│                                      │  Port: 3000  │                      │
│                                      └──────────────┘                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Communication Patterns

| Hop | From → To | Protocol | Pattern | Interval |
|-----|-----------|----------|---------|----------|
| 1 | Simulator → Mosquitto | MQTT (TCP) | **Push** (Publish) | Every 5s |
| 2 | Mosquitto → Telegraf | MQTT (TCP) | **Push** (Subscribe) | Real-time |
| 3 | Prometheus → Telegraf | HTTP | **Pull** (Scrape) | Every 5s |
| 4 | Grafana → Prometheus | HTTP | **Pull** (PromQL) | Every 5s |

> [!NOTE]
> The system uses **two different data delivery paradigms**: push-based MQTT for IoT telemetry ingestion, and pull-based HTTP scraping for metrics collection. Telegraf acts as the **protocol bridge** between these two worlds.

---

## 3. Data Pipeline — End-to-End Flow

This section traces a single data point from generation to dashboard display.

### Step-by-Step Data Journey

```
Step 1: DATA GENERATION
────────────────────────────────────────────────
PLC Simulator generates a JSON payload with 6 sensor readings.
Frequency: Every 5 seconds.

    {
        "temperature": 78,         ← random int [60, 95]
        "pressure": 25,            ← random int [15, 35]
        "humidity": 52,            ← random int [30, 70]
        "motor_rpm": 2100,         ← random int [1000, 3000]
        "vibration": 2.34,         ← random float [0.5, 5.0]
        "power_kw": 98.76          ← random float [50, 150]
    }


Step 2: MQTT PUBLISH
────────────────────────────────────────────────
Simulator publishes the JSON string to the Mosquitto broker.
    Protocol:   MQTT v3.1.1/v5 over TCP
    Host:       mosquitto (Docker DNS)
    Port:       1883
    Topic:      factory/plc1
    QoS:        0 (at most once, default)
    Retain:     false


Step 3: MQTT BROKER ROUTING
────────────────────────────────────────────────
Mosquitto receives the message and fans it out to all
subscribers registered on the "factory/plc1" topic.
    Mode:       Anonymous access (no auth)
    Listener:   0.0.0.0:1883
    Subscriber: Telegraf


Step 4: TELEGRAF CONSUMPTION & TRANSFORMATION
────────────────────────────────────────────────
Telegraf's mqtt_consumer input plugin receives the JSON message.
It parses the JSON and converts each field into a Prometheus metric:

    MQTT JSON field          →   Prometheus metric name
    ─────────────────────────────────────────────────────
    temperature              →   mqtt_consumer_temperature
    pressure                 →   mqtt_consumer_pressure
    humidity                 →   mqtt_consumer_humidity
    motor_rpm                →   mqtt_consumer_motor_rpm
    vibration                →   mqtt_consumer_vibration
    power_kw                 →   mqtt_consumer_power_kw

Naming convention: {input_plugin}_{json_field_name}
These metrics are exposed on an HTTP endpoint at :9273/metrics.


Step 5: PROMETHEUS SCRAPE
────────────────────────────────────────────────
Prometheus scrapes Telegraf's /metrics endpoint every 5 seconds.
    Target:     telegraf:9273
    Job name:   telegraf
    Scrape Interval: 5s

Sample scraped output:
    # HELP mqtt_consumer_temperature Telegraf collected metric
    # TYPE mqtt_consumer_temperature untyped
    mqtt_consumer_temperature{host="..."} 78
    mqtt_consumer_pressure{host="..."} 25
    ...

Prometheus stores these as time-series data points with timestamps.


Step 6: GRAFANA QUERY & VISUALIZATION
────────────────────────────────────────────────
Grafana queries Prometheus using PromQL expressions.
    Dashboard refresh: Every 5s
    Time range: Last 15 minutes (default)

    Panel PromQL queries:
        mqtt_consumer_temperature
        mqtt_consumer_pressure
        mqtt_consumer_humidity
        mqtt_consumer_motor_rpm

Data is rendered as gauge panels and time-series trend charts.
```

---

## 4. Component Deep-Dives

### 4.1 PLC Simulator (Data Source)

| Property | Value |
|----------|-------|
| **Language** | Python 3.11 |
| **Dependency** | `paho-mqtt >= 2.1.0` |
| **Docker Image** | Custom (built from `./simulator/Dockerfile`) |
| **Restart Policy** | `on-failure` |
| **Source File** | `simulator/plc_simulator.py` |

#### What It Does

The PLC simulator mimics a real industrial PLC/sensor gateway. In production, this component would be replaced by actual PLC hardware (e.g., Siemens S7, Allen-Bradley) communicating via OPC-UA or Modbus, with an edge gateway converting to MQTT.

#### Sensor Data Specification

| Sensor | JSON Field | Data Type | Range | Unit | Description |
|--------|-----------|-----------|-------|------|-------------|
| Temperature | `temperature` | Integer | 60 – 95 | °C | Machine/ambient temperature |
| Pressure | `pressure` | Integer | 15 – 35 | PSI | Hydraulic/pneumatic pressure |
| Humidity | `humidity` | Integer | 30 – 70 | % | Ambient relative humidity |
| Motor RPM | `motor_rpm` | Integer | 1000 – 3000 | RPM | Electric motor rotational speed |
| Vibration | `vibration` | Float (2dp) | 0.5 – 5.0 | mm/s | Machine vibration level |
| Power | `power_kw` | Float (2dp) | 50 – 150 | kW | Electrical power consumption |

#### Code Flow

```python
# 1. Initialize MQTT client with v2 callback API
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

# 2. Connect to Mosquitto broker via Docker DNS
client.connect("mosquitto", 1883, 60)     # host, port, keepalive

# 3. Infinite loop — publish every 5 seconds
while True:
    payload = { ... }                      # Generate random sensor data
    client.publish("factory/plc1", json.dumps(payload))
    print(payload)                         # Console logging
    time.sleep(5)                          # 5-second interval
```

#### Dockerfile Breakdown

```dockerfile
FROM python:3.11-slim          # Lightweight Python base image
WORKDIR /app                   # Set working directory
COPY pyproject.toml .          # Copy dependency manifest
RUN pip install --no-cache-dir paho-mqtt>=2.1.0   # Install MQTT client
COPY plc_simulator.py .        # Copy application code
CMD ["python", "-u", "plc_simulator.py"]          # Run unbuffered
```

> [!TIP]
> The `-u` flag runs Python in **unbuffered mode**, ensuring `print()` statements appear immediately in `docker compose logs` — critical for real-time debugging.

---

### 4.2 Eclipse Mosquitto (MQTT Broker)

| Property | Value |
|----------|-------|
| **Docker Image** | `eclipse-mosquitto:2` |
| **Protocol** | MQTT 3.1.1 / 5.0 |
| **Port** | `1883` (TCP, no TLS) |
| **Config File** | `mosquitto/mosquitto.conf` |

#### Configuration

```
listener 1883              # Listen on all interfaces, port 1883
allow_anonymous true       # No username/password required
```

#### Role in the Pipeline

Mosquitto is the **central message broker** implementing the publish-subscribe pattern:

1. **Receives** messages published by the simulator on topic `factory/plc1`
2. **Routes** messages to all subscribers (Telegraf) listening on that topic
3. **Decouples** the data producer from consumers — the simulator doesn't need to know who is reading the data

#### Topic Structure

```
factory/
  └── plc1          ← Current topic (single PLC)
  └── plc2          ← Future expansion (additional PLCs)
  └── plc3          ← Future expansion
```

> [!WARNING]
> The broker is configured with `allow_anonymous true` and **no TLS encryption**. This is acceptable for a local Docker development environment but **must be secured** before any production deployment. See the [Operational Runbook](#11-operational-runbook) for production hardening guidance.

---

### 4.2.1 How MQTT Publish/Subscribe Works — Deep Dive

MQTT uses a **publish/subscribe (pub/sub)** messaging pattern. Understanding this is critical because it underpins the entire data pipeline in this project.

#### The Three Roles in MQTT

```
  PUBLISHER              BROKER               SUBSCRIBER
  (PLC Simulator)        (Mosquitto)          (Telegraf)

  "I have data,          "I'll hold it        "Give me everything
   send it to            and route it         on topic
   topic factory/plc1"   to whoever           factory/plc1"
                         is interested"
```

| Role | Component in This Project | Responsibility |
|------|--------------------------|----------------|
| **Publisher** | `plc_simulator.py` | Generates sensor data and sends it to a topic |
| **Broker** | Mosquitto (Eclipse) | Receives published messages, matches them to subscriptions, forwards to subscribers |
| **Subscriber** | Telegraf (`mqtt_consumer`) | Registers interest in a topic and receives all messages published to it |

#### Step-by-Step — Tracing the Actual Code

**File: `simulator/plc_simulator.py`**

```python
# STEP 1: Import the MQTT client library
import paho.mqtt.client as mqtt

# STEP 2: Create an MQTT client instance (this is the "publisher")
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

# STEP 3: Connect to the broker (Mosquitto container)
client.connect("mosquitto", 1883, 60)
#              ▲            ▲     ▲
#              │            │     └── keepalive: "ping me every 60s to stay alive"
#              │            └── port: standard MQTT port
#              └── hostname: Docker DNS resolves "mosquitto" to the container's IP

# STEP 4: Infinite loop — publish every 5 seconds
while True:
    payload = {
        "temperature": random.randint(60, 95),
        "pressure": random.randint(15, 35),
        ...
    }

    # STEP 5: PUBLISH — this is the key line
    client.publish("factory/plc1", json.dumps(payload))
    #              ▲               ▲
    #              │               └── message: JSON string (the actual data)
    #              └── topic: the "address" or "channel" for this data

    time.sleep(5)  # wait 5 seconds, then repeat
```

#### What Happens at the Network Level

**Phase 1: Connection Establishment (one-time, at startup)**

```
  Simulator                          Mosquitto
     │                                  │
     │──── TCP SYN ────────────────────►│  Port 1883
     │◄─── TCP SYN-ACK ───────────────│
     │──── TCP ACK ────────────────────►│
     │                                  │
     │  TCP connection established      │
     │                                  │
     │──── MQTT CONNECT ──────────────►│  "Hi, I'm a client, let me in"
     │     (client ID, keepalive=60)    │
     │                                  │
     │◄─── MQTT CONNACK ──────────────│  "OK, you're connected"
     │     (return code: 0 = success)   │
     │                                  │
```

**Phase 2: Publishing Messages (every 5 seconds, forever)**

```
  Simulator                          Mosquitto
     │                                  │
     │──── MQTT PUBLISH ──────────────►│
     │     Topic: "factory/plc1"       │
     │     Payload: {"temperature":78, │
     │               "pressure":25,    │
     │               "humidity":52,    │
     │               "motor_rpm":2100, │
     │               "vibration":2.34, │
     │               "power_kw":98.76} │
     │     QoS: 0 (fire and forget)    │
     │                                  │
     │  (no acknowledgment at QoS 0)   │
     │                                  │
     │     ... 5 seconds later ...      │
     │                                  │
     │──── MQTT PUBLISH ──────────────►│
     │     Topic: "factory/plc1"       │
     │     Payload: {"temperature":82, │
     │               "pressure":28...} │
     │                                  │
     │     ... repeats forever ...      │
```

**Phase 3: Broker Routing to Subscriber (Telegraf)**

Meanwhile, Telegraf has already subscribed to the same topic via its configuration:

```toml
# File: telegraf/telegraf.conf
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]    # Connect to the same broker
  topics = ["factory/plc1"]             # "I want messages from this topic"
  data_format = "json"                  # "Parse the payload as JSON"
```

The complete message flow:

```
  Simulator                  Mosquitto                  Telegraf
     │                          │                          │
     │                          │◄── MQTT SUBSCRIBE ──────│
     │                          │    topic: factory/plc1    │
     │                          │                          │
     │                          │──── MQTT SUBACK ────────►│
     │                          │    "OK, you're           │
     │                          │     subscribed"          │
     │                          │                          │
     │  MQTT PUBLISH            │                          │
     │  topic: factory/plc1     │                          │
     │  payload: {temp:78,...}  │                          │
     │─────────────────────────►│                          │
     │                          │                          │
     │                          │  "Who's subscribed to    │
     │                          │   factory/plc1?"         │
     │                          │                          │
     │                          │  → Telegraf is!          │
     │                          │                          │
     │                          │  MQTT PUBLISH (fan-out)  │
     │                          │  topic: factory/plc1     │
     │                          │  payload: {temp:78,...}  │
     │                          │─────────────────────────►│
     │                          │                          │
     │                          │                  Parse JSON:
     │                          │                  temp → mqtt_consumer_temperature = 78
     │                          │                  pressure → mqtt_consumer_pressure = 25
     │                          │                  humidity → mqtt_consumer_humidity = 52
     │                          │                  motor_rpm → mqtt_consumer_motor_rpm = 2100
     │                          │                  vibration → mqtt_consumer_vibration = 2.34
     │                          │                  power_kw → mqtt_consumer_power_kw = 98.76
     │                          │                          │
```

#### The Pub/Sub Pattern — Why It Matters

The key design principle is that the **publisher doesn't know who's listening**, and the **subscriber doesn't know who's publishing**:

```
  WITHOUT Pub/Sub (direct connection):
  ════════════════════════════════════
  Simulator ──────► Telegraf          Simulator MUST know Telegraf's address
                                      If Telegraf dies, Simulator breaks
                                      Adding a new consumer = code change


  WITH Pub/Sub (MQTT broker in the middle):
  ═════════════════════════════════════════
  Simulator ──► Mosquitto ──► Telegraf         Simulator only knows the broker
                          ──► Future App       Adding new consumers = zero code changes
                          ──► Future DB        Simulator doesn't know or care who reads
                          ──► Future Alert Svc

  If Telegraf dies:  Simulator keeps publishing (no error, no impact)
  If Simulator dies: Telegraf keeps running (just no new data arriving)
  If Mosquitto dies: Both sides reconnect automatically when it's back
```

This **decoupling** is why MQTT is the dominant protocol in IoT — producers and consumers are completely independent of each other.

#### MQTT Concept Reference

| Concept | In This Project | What It Does |
|---------|----------------|-------------|
| **Client** | `mqtt.Client()` in `plc_simulator.py` | Creates an MQTT publisher instance |
| **Connect** | `client.connect("mosquitto", 1883, 60)` | Opens a persistent TCP connection to the broker |
| **Topic** | `"factory/plc1"` | A named channel — like a TV channel or a mailbox address |
| **Payload** | `json.dumps(payload)` | The actual data being sent (serialized as a JSON string) |
| **Publish** | `client.publish(topic, payload)` | Sends one message to the broker on the specified topic |
| **Subscribe** | Telegraf's `topics = ["factory/plc1"]` | Registers interest in a topic — "send me everything on this channel" |
| **QoS 0** | Default (not explicitly set) | "Fire and forget" — no delivery confirmation, fastest |
| **QoS 1** | Not used yet | "At least once" — broker confirms delivery, may duplicate |
| **QoS 2** | Not used yet | "Exactly once" — guaranteed single delivery, slowest |
| **Broker** | Mosquitto container | The central hub that receives, routes, and delivers messages |
| **Keepalive** | `60` seconds | Client pings the broker every 60s to keep the connection alive |

> [!NOTE]
> **Why QoS 0 is acceptable for this project**: In real-time monitoring, a missing data point every few hours is tolerable — the next reading arrives 5 seconds later. QoS 0 provides the lowest latency and least overhead. For critical alerts or commands (e.g., emergency stops), QoS 1 or 2 should be used.

---

### 4.3 Telegraf (Metrics Bridge)

| Property | Value |
|----------|-------|
| **Docker Image** | `telegraf:latest` |
| **Role** | MQTT → Prometheus bridge |
| **Input** | MQTT Consumer (subscribes to `factory/plc1`) |
| **Output** | Prometheus Client (HTTP endpoint on `:9273`) |
| **Config File** | `telegraf/telegraf.conf` |

#### Configuration Breakdown

```toml
[agent]
  interval = "5s"                          # Collection interval

[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]       # MQTT broker address (Docker DNS)
  topics = ["factory/plc1"]               # Subscribe to PLC topic
  data_format = "json"                     # Parse incoming payload as JSON

[[outputs.prometheus_client]]
  listen = ":9273"                         # Expose metrics on HTTP port 9273
```

#### Transformation Logic

Telegraf performs the critical **protocol translation** in this pipeline:

```
                    ┌──────────────────────┐
   MQTT Message     │                      │    HTTP /metrics
   (Push, JSON)  ──►│  TELEGRAF             │──► (Pull, Prometheus
                    │                      │    text format)
                    │  1. Subscribe MQTT    │
                    │  2. Parse JSON        │
                    │  3. Convert to        │
                    │     Prometheus format │
                    │  4. Serve on :9273    │
                    └──────────────────────┘
```

**Metric Naming Convention**:

Telegraf auto-generates metric names using the pattern:
```
{input_plugin_name}_{json_field_name}
```

Example: Input plugin = `mqtt_consumer`, JSON field = `temperature` → Metric = `mqtt_consumer_temperature`

#### Exposed `/metrics` Endpoint (Sample Output)

```
# HELP mqtt_consumer_temperature Telegraf collected metric
# TYPE mqtt_consumer_temperature untyped
mqtt_consumer_temperature{host="telegraf-container",topic="factory/plc1"} 78

# HELP mqtt_consumer_pressure Telegraf collected metric
# TYPE mqtt_consumer_pressure untyped
mqtt_consumer_pressure{host="telegraf-container",topic="factory/plc1"} 25

# HELP mqtt_consumer_humidity Telegraf collected metric
# TYPE mqtt_consumer_humidity untyped
mqtt_consumer_humidity{host="telegraf-container",topic="factory/plc1"} 52

# HELP mqtt_consumer_motor_rpm Telegraf collected metric
# TYPE mqtt_consumer_motor_rpm untyped
mqtt_consumer_motor_rpm{host="telegraf-container",topic="factory/plc1"} 2100

# HELP mqtt_consumer_vibration Telegraf collected metric
# TYPE mqtt_consumer_vibration untyped
mqtt_consumer_vibration{host="telegraf-container",topic="factory/plc1"} 2.34

# HELP mqtt_consumer_power_kw Telegraf collected metric
# TYPE mqtt_consumer_power_kw untyped
mqtt_consumer_power_kw{host="telegraf-container",topic="factory/plc1"} 98.76
```

---

### 4.4 Prometheus (Time-Series Database)

| Property | Value |
|----------|-------|
| **Docker Image** | `prom/prometheus` |
| **Role** | Scrape, store, and query time-series metrics |
| **Port** | `9090` (Web UI + API) |
| **Config File** | `prometheus/prometheus.yml` |
| **Storage** | In-container (ephemeral, no volume mount) |

#### Configuration

```yaml
global:
  scrape_interval: 5s          # Scrape all targets every 5 seconds

scrape_configs:
  - job_name: telegraf          # Logical name for this scrape job
    static_configs:
      - targets:
          - telegraf:9273       # Telegraf's Prometheus client endpoint
```

#### How Prometheus Works in This Pipeline

1. **Scrapes**: Every 5 seconds, Prometheus sends an HTTP GET request to `http://telegraf:9273/metrics`
2. **Parses**: Reads the Prometheus text exposition format
3. **Stores**: Appends each metric value with a timestamp to its internal TSDB (time-series database)
4. **Serves**: Exposes a PromQL query API that Grafana uses to retrieve data

#### Important Labels Added by Prometheus

| Label | Value | Added By |
|-------|-------|----------|
| `job` | `telegraf` | Prometheus (from `job_name`) |
| `instance` | `telegraf:9273` | Prometheus (from `targets`) |
| `host` | Container hostname | Telegraf |
| `topic` | `factory/plc1` | Telegraf |

> [!IMPORTANT]
> Prometheus storage is **ephemeral** in this setup — data is lost when the container restarts. For production, mount a persistent volume:
> ```yaml
> volumes:
>   - prometheus_data:/prometheus
> ```

---

### 4.5 Grafana (Visualization)

| Property | Value |
|----------|-------|
| **Docker Image** | `grafana/grafana:latest` |
| **Port** | `3000` |
| **Admin User** | `admin` |
| **Admin Password** | `admin123` |
| **Data Source** | Prometheus (auto-provisioned or manual) |
| **Dashboard** | Factory Metrics Dashboard (auto-provisioned) |

#### Volume Mounts

| Mount | Purpose |
|-------|---------|
| `grafana_data:/var/lib/grafana` | Persistent storage for Grafana DB, plugins, etc. |
| `./grafana/provisioning:/etc/grafana/provisioning` | Dashboard provisioning configuration |
| `./grafana/dashboards:/etc/grafana/provisioning/dashboards` | Dashboard JSON files |

#### Dashboard Provisioning

The dashboard auto-loads via Grafana's provisioning system:

**`grafana/provisioning/dashboards/dashboard.yml`**:
```yaml
apiVersion: 1
providers:
  - name: Factory Dashboard
    orgId: 1
    folder: Factory
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    options:
      path: /etc/grafana/provisioning/dashboards/json
```

This tells Grafana to scan `/etc/grafana/provisioning/dashboards/json` every 10 seconds for dashboard JSON files and automatically load them into the "Factory" folder.

---

## 5. Data Formats & Transformations

### Stage 1: JSON (Simulator → MQTT Broker)

```json
{
    "temperature": 78,
    "pressure": 25,
    "humidity": 52,
    "motor_rpm": 2100,
    "vibration": 2.34,
    "power_kw": 98.76
}
```

- **Format**: Flat JSON object
- **Encoding**: UTF-8 string
- **Transport**: MQTT message payload on topic `factory/plc1`

### Stage 2: Prometheus Text Exposition (Telegraf → Prometheus)

```
# TYPE mqtt_consumer_temperature untyped
mqtt_consumer_temperature{host="abc123",topic="factory/plc1"} 78 1718358300000
```

- **Format**: Prometheus exposition format v0.0.4
- **Transport**: HTTP response body from `GET /metrics`
- **Content-Type**: `text/plain; version=0.0.4`

### Stage 3: Time-Series Data Points (Prometheus Internal)

```
Series: mqtt_consumer_temperature{host="abc123",topic="factory/plc1",job="telegraf",instance="telegraf:9273"}
Samples:
    (1718358300, 78)
    (1718358305, 82)
    (1718358310, 71)
    ...
```

- **Format**: TSDB blocks (WAL + compacted chunks)
- **Indexed by**: Metric name + label set

### Stage 4: PromQL Query Results (Prometheus → Grafana)

```json
{
    "status": "success",
    "data": {
        "resultType": "vector",
        "result": [
            {
                "metric": {
                    "__name__": "mqtt_consumer_temperature",
                    "host": "abc123",
                    "topic": "factory/plc1"
                },
                "value": [1718358300, "78"]
            }
        ]
    }
}
```

- **Format**: JSON (Prometheus HTTP API response)
- **Transport**: HTTP response from `GET /api/v1/query`

### Transformation Summary

```
JSON ──MQTT──► JSON ──Parse──► Internal Metrics ──HTTP──► Prometheus Text
                                                             │
                                                    Scrape & Store
                                                             │
                                                          PromQL
                                                             │
                                                   JSON API Response
                                                             │
                                                     Grafana Panels
```

---

## 6. Network Topology & Port Map

### Internal Docker Network (Service-to-Service)

All containers communicate over Docker Compose's default bridge network using **service names as DNS hostnames**.

| Service | Internal Hostname | Internal Port | Protocol |
|---------|------------------|---------------|----------|
| Mosquitto | `mosquitto` | 1883 | MQTT/TCP |
| Simulator | `simulator` | — | — (client only) |
| Telegraf | `telegraf` | 9273 | HTTP |
| Prometheus | `prometheus` | 9090 | HTTP |
| Grafana | `grafana` | 3000 | HTTP |

### External Access (Host Machine)

| Service | Host URL | Purpose |
|---------|----------|---------|
| Mosquitto | `localhost:1883` | MQTT client testing |
| Telegraf | `localhost:9273` | Verify raw metrics |
| Prometheus | `http://localhost:9090` | Query UI, target status |
| Grafana | `http://localhost:3000` | Dashboard viewing |

### Connection Diagram

```
Host Machine (localhost)
    │
    ├── :1883  ─────► Mosquitto Container  ◄──── Simulator Container
    │                        │
    │                        └──────────────────► Telegraf Container
    │                                                  │
    ├── :9273  ─────► Telegraf Container  ◄──── Prometheus Container
    │                                                  │
    ├── :9090  ─────► Prometheus Container  ◄──── Grafana Container
    │
    └── :3000  ─────► Grafana Container
```

---

## 7. Docker Orchestration

### Service Dependency Graph

```
                    mosquitto
                   /         \
                  ▼           ▼
           simulator       telegraf
                              │
                              ▼
                          prometheus
                              │
                              ▼
                           grafana
```

### `depends_on` Chain

| Service | Depends On | Reason |
|---------|-----------|--------|
| `simulator` | `mosquitto` | Must connect to MQTT broker |
| `telegraf` | `mosquitto` | Must subscribe to MQTT topics |
| `prometheus` | — | Standalone (scrapes on interval) |
| `grafana` | `prometheus` | Needs data source available |

### Container Startup Order

1. **mosquitto** — Starts first (no dependencies)
2. **simulator** + **telegraf** — Start after Mosquitto is created
3. **prometheus** — Starts independently
4. **grafana** — Starts after Prometheus is created

> [!NOTE]
> `depends_on` only waits for container **creation**, not readiness. The `restart: on-failure` policy on the simulator handles cases where Mosquitto isn't ready yet by automatically restarting the container.

### Volume Configuration

| Volume | Type | Mount Path | Purpose |
|--------|------|-----------|---------|
| `grafana_data` | Named volume | `/var/lib/grafana` | Persist Grafana database, dashboards, plugins |
| `./mosquitto/mosquitto.conf` | Bind mount | `/mosquitto/config/mosquitto.conf` | Mosquitto configuration |
| `./telegraf/telegraf.conf` | Bind mount (read-only) | `/etc/telegraf/telegraf.conf` | Telegraf configuration |
| `./prometheus/prometheus.yml` | Bind mount | `/etc/prometheus/prometheus.yml` | Prometheus configuration |
| `./grafana/provisioning` | Bind mount | `/etc/grafana/provisioning` | Grafana provisioning configs |
| `./grafana/dashboards` | Bind mount | `/etc/grafana/provisioning/dashboards` | Dashboard JSON files |

---

## 8. Grafana Dashboard Specification

### Dashboard: "Factory Metrics Dashboard"

| Property | Value |
|----------|-------|
| **Title** | Factory Metrics Dashboard |
| **Refresh** | Every 5 seconds |
| **Time Range** | Last 15 minutes |
| **Timezone** | Browser |
| **Schema Version** | 41 |
| **Tags** | `factory`, `mqtt`, `prometheus`, `industrial` |

### Panel Layout

```
Row 1 (y=0, h=8): Gauge Panels
┌─────────────┬─────────────┬─────────────┬─────────────┐
│ Temperature │  Pressure   │  Humidity   │  Motor RPM  │
│   (Gauge)   │   (Gauge)   │   (Gauge)   │   (Gauge)   │
│   w=6       │   w=6       │   w=6       │   w=6       │
│  ID: 1      │  ID: 2      │  ID: 3      │  ID: 4      │
└─────────────┴─────────────┴─────────────┴─────────────┘

Row 2 (y=8, h=10): Time-Series Trend Charts
┌──────────────────────────┬──────────────────────────┐
│   Temperature Trend      │   Pressure Trend         │
│   (Time-Series)          │   (Time-Series)          │
│   w=12                   │   w=12                   │
│   ID: 5                  │   ID: 6                  │
└──────────────────────────┴──────────────────────────┘

Row 3 (y=18, h=10): Time-Series Trend Charts
┌──────────────────────────┬──────────────────────────┐
│   Humidity Trend         │   Motor RPM Trend        │
│   (Time-Series)          │   (Time-Series)          │
│   w=12                   │   w=12                   │
│   ID: 7                  │   ID: 8                  │
└──────────────────────────┴──────────────────────────┘
```

### Panel Details

| ID | Panel | Type | PromQL Query | Unit | Min | Max | Thresholds |
|----|-------|------|-------------|------|-----|-----|------------|
| 1 | Temperature | Gauge | `mqtt_consumer_temperature` | °C | 0 | 100 | Green < 75, Yellow 75–85, Red > 85 |
| 2 | Pressure | Gauge | `mqtt_consumer_pressure` | PSI | 0 | 50 | — |
| 3 | Humidity | Gauge | `mqtt_consumer_humidity` | % | 0 | 100 | — |
| 4 | Motor RPM | Gauge | `mqtt_consumer_motor_rpm` | RPM | 0 | 3000 | — |
| 5 | Temperature Trend | Time-Series | `mqtt_consumer_temperature` | °C | — | — | — |
| 6 | Pressure Trend | Time-Series | `mqtt_consumer_pressure` | PSI | — | — | — |
| 7 | Humidity Trend | Time-Series | `mqtt_consumer_humidity` | % | — | — | — |
| 8 | Motor RPM Trend | Time-Series | `mqtt_consumer_motor_rpm` | RPM | — | — | — |

### Time-Series Legend Configuration

All trend panels display a **table legend** at the bottom with these aggregations:

| Aggregation | Description |
|-------------|-------------|
| `last` | Most recent value |
| `min` | Minimum in time range |
| `max` | Maximum in time range |
| `mean` | Average over time range |

---

## 9. Sequence Diagram — Complete Data Journey

```
    Simulator          Mosquitto           Telegraf          Prometheus         Grafana
       │                  │                  │                  │                 │
       │  MQTT CONNECT    │                  │                  │                 │
       │─────────────────►│                  │                  │                 │
       │  CONNACK         │                  │                  │                 │
       │◄─────────────────│                  │                  │                 │
       │                  │                  │                  │                 │
       │                  │  MQTT SUBSCRIBE  │                  │                 │
       │                  │◄─────────────────│                  │                 │
       │                  │  SUBACK          │                  │                 │
       │                  │─────────────────►│                  │                 │
       │                  │                  │                  │                 │
  ┌────┤  (every 5s loop) │                  │                  │                 │
  │    │                  │                  │                  │                 │
  │    │  PUBLISH         │                  │                  │                 │
  │    │  topic:plc1      │                  │                  │                 │
  │    │  payload:{JSON}  │                  │                  │                 │
  │    │─────────────────►│                  │                  │                 │
  │    │                  │                  │                  │                 │
  │    │                  │  PUBLISH (fan-out)│                  │                 │
  │    │                  │  topic:plc1      │                  │                 │
  │    │                  │  payload:{JSON}  │                  │                 │
  │    │                  │─────────────────►│                  │                 │
  │    │                  │                  │                  │                 │
  │    │                  │                  │  Parse JSON       │                 │
  │    │                  │                  │  Convert to       │                 │
  │    │                  │                  │  Prometheus fmt   │                 │
  │    │                  │                  │  Update /metrics  │                 │
  │    │                  │                  │                  │                 │
  │    │                  │                  │  HTTP GET /metrics│                 │
  │    │                  │                  │◄─────────────────│                 │
  │    │                  │                  │                  │                 │
  │    │                  │                  │  200 OK          │                 │
  │    │                  │                  │  (text/plain)    │                 │
  │    │                  │                  │─────────────────►│                 │
  │    │                  │                  │                  │                 │
  │    │                  │                  │                  │  Store in TSDB   │
  │    │                  │                  │                  │                 │
  │    │                  │                  │                  │  PromQL Query   │
  │    │                  │                  │                  │◄────────────────│
  │    │                  │                  │                  │                 │
  │    │                  │                  │                  │  JSON Response  │
  │    │                  │                  │                  │────────────────►│
  │    │                  │                  │                  │                 │
  │    │                  │                  │                  │  Render Panels  │
  │    │                  │                  │                  │                 │
  └────┤                  │                  │                  │                 │
       │                  │                  │                  │                 │
```

---

## 10. Configuration Reference

### Complete File Map

```
IIOT/
├── docker-compose.yml                          # Orchestrates all 5 services
├── .gitignore                                  # Python artifacts exclusions
│
├── simulator/
│   ├── plc_simulator.py                        # PLC sensor data generator
│   ├── Dockerfile                              # Container build instructions
│   ├── pyproject.toml                          # Python project & dependencies
│   ├── uv.lock                                 # Dependency lock file (uv)
│   ├── .python-version                         # Python version pin (3.11)
│   ├── .gitignore                              # Simulator-specific ignores
│   └── README.md                               # (empty)
│
├── mosquitto/
│   └── mosquitto.conf                          # MQTT broker configuration
│
├── telegraf/
│   └── telegraf.conf                           # Metrics bridge configuration
│
├── prometheus/
│   └── prometheus.yml                          # Scrape target configuration
│
└── grafana/
    ├── dashboards/
    │   └── factory-dashboard.json              # Dashboard panel definitions
    └── provisioning/
        └── dashboards/
            └── dashboard.yml                   # Auto-provisioning config
```

### Environment Variables

| Variable | Service | Value | Purpose |
|----------|---------|-------|---------|
| `GF_SECURITY_ADMIN_USER` | Grafana | `admin` | Admin login username |
| `GF_SECURITY_ADMIN_PASSWORD` | Grafana | `admin123` | Admin login password |

### Key Intervals & Timeouts

| Parameter | Value | Configured In | Description |
|-----------|-------|---------------|-------------|
| Simulator publish interval | 5s | `plc_simulator.py` (`time.sleep(5)`) | How often new data is generated |
| MQTT keepalive | 60s | `plc_simulator.py` (`client.connect(…, 60)`) | MQTT connection keepalive |
| Telegraf collection interval | 5s | `telegraf.conf` (`interval = "5s"`) | Agent polling interval |
| Prometheus scrape interval | 5s | `prometheus.yml` (`scrape_interval: 5s`) | How often Prometheus scrapes |
| Grafana dashboard refresh | 5s | `factory-dashboard.json` (`"refresh": "5s"`) | Dashboard auto-refresh |
| Dashboard provisioning scan | 10s | `dashboard.yml` (`updateIntervalSeconds: 10`) | Grafana re-scans for JSON changes |

---

## 11. Operational Runbook

### Starting the Stack

```bash
# Build and start all services in detached mode
docker compose up -d --build

# View logs from all services
docker compose logs -f

# View logs from a specific service
docker compose logs -f simulator
docker compose logs -f telegraf
```

### Verifying the Pipeline

```bash
# Step 1: Check if the simulator is publishing data
docker compose logs simulator
# Expected: JSON payloads printed every 5 seconds

# Step 2: Verify MQTT messages are flowing
# (Requires mosquitto-clients installed on host)
mosquitto_sub -h localhost -p 1883 -t "factory/plc1"
# Expected: JSON payloads appearing every 5 seconds

# Step 3: Check Telegraf metrics endpoint
curl http://localhost:9273/metrics | grep mqtt_consumer
# Expected: mqtt_consumer_temperature, mqtt_consumer_pressure, etc.

# Step 4: Verify Prometheus is scraping
# Open http://localhost:9090/targets
# Expected: telegraf:9273 target with status "UP"

# Step 5: Query Prometheus directly
curl 'http://localhost:9090/api/v1/query?query=mqtt_consumer_temperature'
# Expected: JSON response with current temperature value

# Step 6: Access Grafana dashboard
# Open http://localhost:3000
# Login: admin / admin123
# Navigate to Factory folder → Factory Metrics Dashboard
```

### Stopping the Stack

```bash
# Stop all containers
docker compose down

# Stop and remove volumes (resets Grafana data)
docker compose down -v
```

### Production Hardening Checklist

- [ ] **Mosquitto**: Enable TLS (port 8883) and username/password authentication
- [ ] **Mosquitto**: Disable `allow_anonymous`
- [ ] **Grafana**: Change default admin password
- [ ] **Grafana**: Configure OAuth or LDAP authentication
- [ ] **Prometheus**: Add persistent volume for data retention
- [ ] **Prometheus**: Configure retention period (`--storage.tsdb.retention.time`)
- [ ] **Telegraf**: Add TLS certificates for MQTT connection
- [ ] **Network**: Use custom Docker network with isolation
- [ ] **Simulator**: Replace with real PLC/OPC-UA gateway
- [ ] **Alerting**: Configure Grafana alerting rules for threshold breaches

---

## 12. Troubleshooting Guide

### Common Issues

| Symptom | Likely Cause | Solution |
|---------|-------------|----------|
| Simulator keeps restarting | Mosquitto not ready | Wait ~10s, `restart: on-failure` handles this automatically |
| No data in Grafana | Prometheus not scraping | Check `http://localhost:9090/targets` for errors |
| Telegraf metrics empty | MQTT subscription failed | Check Telegraf logs: `docker compose logs telegraf` |
| Grafana shows "No Data" | Data source not configured | Add Prometheus data source: URL = `http://prometheus:9090` |
| Dashboard not appearing | Provisioning path mismatch | Verify JSON file is in the correct mount path |
| Stale data in Grafana | Refresh interval too high | Ensure dashboard refresh is set to `5s` |

### Diagnostic Commands

```bash
# Check container status
docker compose ps

# Check Docker network connectivity
docker compose exec telegraf ping mosquitto
docker compose exec grafana ping prometheus

# Inspect Telegraf internal metrics
docker compose exec telegraf telegraf --test

# Check Prometheus configuration
curl http://localhost:9090/api/v1/status/config

# List all Prometheus metrics
curl http://localhost:9090/api/v1/label/__name__/values | python -m json.tool
```

---

## 13. Glossary

| Term | Definition |
|------|-----------|
| **IIoT** | Industrial Internet of Things — connecting industrial equipment to the internet for monitoring and control |
| **PLC** | Programmable Logic Controller — industrial computer for automation control |
| **MQTT** | Message Queuing Telemetry Transport — lightweight pub/sub messaging protocol for IoT |
| **Broker** | Server that receives messages from publishers and routes them to subscribers |
| **Topic** | Named channel in MQTT used to categorize and route messages (e.g., `factory/plc1`) |
| **QoS** | Quality of Service — MQTT delivery guarantee level (0=at most once, 1=at least once, 2=exactly once) |
| **Telegraf** | InfluxData's agent for collecting, processing, and writing metrics |
| **Prometheus** | Open-source time-series database and monitoring system using a pull-based model |
| **PromQL** | Prometheus Query Language — used to select and aggregate time-series data |
| **TSDB** | Time-Series Database — database optimized for timestamped data |
| **Scrape** | Prometheus's mechanism of periodically pulling metrics from targets via HTTP |
| **Gauge** | Metric type representing a value that can go up and down (e.g., temperature) |
| **Grafana** | Open-source analytics and visualization platform |
| **Provisioning** | Grafana's mechanism for auto-configuring data sources and dashboards from files |
| **Exposition Format** | Prometheus's text-based format for metrics (`metric_name{labels} value timestamp`) |
| **WAL** | Write-Ahead Log — Prometheus's mechanism for durable writes before compaction |

---

> [!TIP]
> **Quick Reference — Data flows in this order:**  
> `Simulator` → *MQTT* → `Mosquitto` → *MQTT* → `Telegraf` → *HTTP* → `Prometheus` → *PromQL* → `Grafana`
