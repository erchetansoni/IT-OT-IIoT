# IIoT Production Implementation Guide

> **Project**: Avgol IIoT Factory Monitoring System  
> **Scope**: Moving from Simulator → Real Factory Floor  
> **Last Updated**: 2026-06-14  

---

## Table of Contents

- [1. Production vs Development — Gap Analysis](#1-production-vs-development--gap-analysis)
- [2. Real PLC & Sensor Connectivity](#2-real-plc--sensor-connectivity)
  - [2.1 Common Industrial PLCs](#21-common-industrial-plcs)
  - [2.2 Industrial Communication Protocols](#22-industrial-communication-protocols)
  - [2.3 OPC-UA — The Preferred Protocol](#23-opc-ua--the-preferred-protocol)
  - [2.4 Modbus TCP/RTU](#24-modbus-tcprtu)
  - [2.5 EtherNet/IP & PROFINET](#25-ethernetip--profinet)
- [3. Edge Gateway Architecture](#3-edge-gateway-architecture)
- [4. Data Formats in Production](#4-data-formats-in-production)
  - [4.1 Raw PLC Register Data](#41-raw-plc-register-data)
  - [4.2 OPC-UA Data Format](#42-opc-ua-data-format)
  - [4.3 Modbus Data Format](#43-modbus-data-format)
  - [4.4 MQTT Payload Standards (SparkplugB)](#44-mqtt-payload-standards-sparkplugb)
  - [4.5 Unified JSON Schema for MQTT](#45-unified-json-schema-for-mqtt)
- [5. Network Architecture & Connectivity](#5-network-architecture--connectivity)
  - [5.1 Purdue Model / ISA-95 Network Layers](#51-purdue-model--isa-95-network-layers)
  - [5.2 Port Reference Table](#52-port-reference-table)
  - [5.3 Firewall Rules](#53-firewall-rules)
  - [5.4 Network Segmentation](#54-network-segmentation)
- [6. Production Architecture](#6-production-architecture)
  - [6.1 Single-Site Deployment](#61-single-site-deployment)
  - [6.2 Multi-Site / Cloud Deployment](#62-multi-site--cloud-deployment)
- [7. How Data Will Be Received in Production](#7-how-data-will-be-received-in-production)
  - [7.1 Scenario A: Direct PLC → MQTT](#71-scenario-a-direct-plc--mqtt)
  - [7.2 Scenario B: PLC → Edge Gateway → MQTT](#72-scenario-b-plc--edge-gateway--mqtt)
  - [7.3 Scenario C: PLC → OPC-UA Server → Telegraf → MQTT](#73-scenario-c-plc--opc-ua-server--telegraf--mqtt)
  - [7.4 Scenario D: Legacy Analog Sensors → IoT Gateway → MQTT](#74-scenario-d-legacy-analog-sensors--iot-gateway--mqtt)
- [8. MQTT Topic Design for Production](#8-mqtt-topic-design-for-production)
- [9. Security Requirements](#9-security-requirements)
  - [9.1 MQTT Broker Security (Mosquitto)](#91-mqtt-broker-security-mosquitto)
  - [9.2 TLS/SSL Certificates](#92-tlsssl-certificates)
  - [9.3 Network Security](#93-network-security)
  - [9.4 Grafana Security](#94-grafana-security)
  - [9.5 Prometheus Security](#95-prometheus-security)
- [10. Data Persistence & Retention](#10-data-persistence--retention)
- [11. High Availability & Redundancy](#11-high-availability--redundancy)
- [12. Alerting & Notifications](#12-alerting--notifications)
- [13. Scaling Considerations](#13-scaling-considerations)
- [14. Production Docker Compose (Reference)](#14-production-docker-compose-reference)
- [15. Production Deployment Checklist](#15-production-deployment-checklist)
- [16. Hardware Requirements](#16-hardware-requirements)
- [17. Vendor-Specific Integration Examples](#17-vendor-specific-integration-examples)
  - [17.1 Siemens S7-1500](#171-siemens-s7-1500)
  - [17.2 Allen-Bradley / Rockwell](#172-allen-bradley--rockwell)
  - [17.3 Mitsubishi MELSEC](#173-mitsubishi-melsec)
  - [17.4 Schneider Electric Modicon](#174-schneider-electric-modicon)

---

## 1. Production vs Development — Gap Analysis

| Aspect | Current (Development) | Required (Production) |
|--------|----------------------|----------------------|
| **Data Source** | Python simulator with `random` values | Real PLCs / sensors on factory floor |
| **Protocol to Broker** | Direct MQTT publish | OPC-UA / Modbus → Edge Gateway → MQTT |
| **MQTT Security** | Anonymous, no TLS | TLS 1.3, X.509 certificates, ACLs |
| **MQTT Broker** | Single Mosquitto container | Clustered broker (EMQX / HiveMQ / VerneMQ) |
| **Data Format** | Simple flat JSON | Sparkplug B or structured JSON with metadata |
| **Network** | Docker bridge network | Segmented IT/OT network (ISA-95 Purdue Model) |
| **Prometheus Storage** | Ephemeral (in-container) | Persistent volume + long-term storage (Thanos/Cortex) |
| **Grafana Auth** | `admin/admin123` | SSO / LDAP / OAuth 2.0 |
| **Alerting** | None | Grafana Alerting → Email / SMS / PagerDuty / Slack |
| **Redundancy** | Single instance of everything | HA pairs, load balancing, failover |
| **Monitoring** | None | Self-monitoring (Prometheus monitors itself) |
| **Deployment** | `docker compose up` | Kubernetes / Docker Swarm on edge servers |
| **Number of PLCs** | 1 simulated | 10–1000+ real PLCs across production lines |
| **Data Volume** | ~6 metrics @ 5s interval | Thousands of tags @ sub-second intervals |

---

## 2. Real PLC & Sensor Connectivity

### 2.1 Common Industrial PLCs

In a real Avgol nonwoven fabric production facility, you'll encounter these types of PLCs and controllers:

| Vendor | PLC Model | Common Protocol | Typical Use |
|--------|-----------|-----------------|-------------|
| **Siemens** | S7-1200 / S7-1500 | OPC-UA, S7comm, PROFINET | Line automation, drives |
| **Allen-Bradley** | CompactLogix / ControlLogix | EtherNet/IP, OPC-UA | Packaging, material handling |
| **Mitsubishi** | MELSEC iQ-R / iQ-F | CC-Link IE, MC Protocol | Spinning, winding machines |
| **Schneider** | Modicon M340 / M580 | Modbus TCP, OPC-UA | Process control, utilities |
| **Beckhoff** | TwinCAT / CX series | ADS, OPC-UA | High-speed motion control |
| **ABB** | AC500 | Modbus TCP, OPC-UA | Motor drives, power monitoring |
| **Omron** | NX/NJ Series | EtherNet/IP, OPC-UA | Packaging, inspection |

### 2.2 Industrial Communication Protocols

```
┌─────────────────────────────────────────────────────────────────────┐
│                  INDUSTRIAL PROTOCOL LANDSCAPE                      │
│                                                                     │
│   Layer 4 (Application):                                            │
│   ┌─────────┐ ┌──────────┐ ┌────────────┐ ┌──────────┐            │
│   │ OPC-UA  │ │ Modbus   │ │ EtherNet/IP│ │ PROFINET │            │
│   │         │ │ TCP/RTU  │ │            │ │          │            │
│   └────┬────┘ └────┬─────┘ └─────┬──────┘ └────┬─────┘            │
│        │           │             │              │                   │
│   Layer 3 (Transport):                                              │
│   ┌────┴───────────┴─────────────┴──────────────┴────┐             │
│   │              TCP/IP (Ethernet)                    │             │
│   └──────────────────────────────────────────────────┘             │
│                          │                                          │
│   Layer 2 (Field Bus / Legacy):                                     │
│   ┌──────────┐ ┌────────────┐ ┌─────────┐ ┌──────────┐            │
│   │ Modbus   │ │ PROFIBUS   │ │ DeviceNet│ │ CC-Link  │            │
│   │ RTU      │ │ DP         │ │          │ │          │            │
│   │ (RS-485) │ │            │ │          │ │          │            │
│   └──────────┘ └────────────┘ └─────────┘ └──────────┘            │
│                                                                     │
│   Layer 1 (Sensor/Analog):                                          │
│   ┌──────────┐ ┌────────────┐ ┌──────────┐ ┌─────────┐            │
│   │ 4-20mA   │ │ 0-10V      │ │ PT100    │ │ Digital  │            │
│   │ Analog   │ │ Analog     │ │ RTD      │ │ I/O      │            │
│   └──────────┘ └────────────┘ └──────────┘ └─────────┘            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Protocol Comparison for This Project

| Protocol | Port | Transport | Best For | Complexity | Recommendation |
|----------|------|-----------|----------|------------|----------------|
| **OPC-UA** | 4840 | TCP | Modern PLCs, unified access | Medium | ⭐ **Preferred** |
| **Modbus TCP** | 502 | TCP | Simple sensors, legacy PLCs | Low | Good for brownfield |
| **EtherNet/IP** | 44818 | TCP/UDP | Allen-Bradley ecosystems | Medium | Vendor-specific |
| **PROFINET** | Dynamic | Ethernet L2 | Siemens ecosystems | High | Vendor-specific |
| **S7comm** | 102 | TCP | Siemens S7 (legacy) | Medium | Use OPC-UA instead |
| **MQTT** | 1883/8883 | TCP | Edge-to-cloud transport | Low | ⭐ Already in use |

### 2.3 OPC-UA — The Preferred Protocol

OPC-UA (Open Platform Communications Unified Architecture) is the **industry standard** for IIoT data exchange. Most modern PLCs have built-in OPC-UA servers.

#### How OPC-UA Works

```
┌──────────────┐         OPC-UA          ┌──────────────┐
│              │     (TCP port 4840)      │              │
│  PLC         │ ◄──────────────────────► │  OPC-UA      │
│  (S7-1500)   │                          │  Client      │
│              │                          │  (Telegraf/  │
│  Built-in    │   Browse / Read /        │   Gateway)   │
│  OPC-UA      │   Subscribe to nodes    │              │
│  Server      │                          │              │
└──────────────┘                          └──────────────┘
```

#### OPC-UA Address Space (Node Structure)

In a real PLC, data is organized in an **address space** — a hierarchical tree of nodes:

```
Root
├── Objects
│   └── DeviceSet
│       └── PLC1
│           ├── Temperature      (NodeId: ns=2;s=PLC1.Temperature)
│           │   ├── Value: 78.5
│           │   ├── DataType: Double
│           │   ├── Timestamp: 2026-06-14T07:30:00Z
│           │   └── Quality: Good
│           │
│           ├── Pressure         (NodeId: ns=2;s=PLC1.Pressure)
│           │   ├── Value: 25.3
│           │   ├── DataType: Double
│           │   └── Quality: Good
│           │
│           ├── Humidity          (NodeId: ns=2;s=PLC1.Humidity)
│           ├── MotorRPM          (NodeId: ns=2;s=PLC1.MotorRPM)
│           ├── Vibration         (NodeId: ns=2;s=PLC1.Vibration)
│           └── PowerKW           (NodeId: ns=2;s=PLC1.PowerKW)
│
└── Types
    └── BaseObjectType
```

#### OPC-UA Connection Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| **Endpoint URL** | `opc.tcp://192.168.1.100:4840` | PLC's OPC-UA server address |
| **Security Mode** | `SignAndEncrypt` | Message signing + encryption |
| **Security Policy** | `Basic256Sha256` | Encryption algorithm |
| **Authentication** | Certificate or Username/Password | Client auth method |
| **Namespace Index** | `ns=2` | Application-specific namespace |
| **Subscription Interval** | 1000 ms | How often server pushes changes |

#### Telegraf OPC-UA Input Plugin (Production Config)

```toml
[[inputs.opcua]]
  ## OPC-UA Server Endpoint
  endpoint = "opc.tcp://192.168.1.100:4840"
  
  ## Connection timeout
  connect_timeout = "10s"
  request_timeout = "5s"
  
  ## Security (production-grade)
  security_policy = "Basic256Sha256"
  security_mode = "SignAndEncrypt"
  certificate = "/etc/telegraf/certs/client.crt"
  private_key = "/etc/telegraf/certs/client.key"
  
  ## Authentication
  auth_method = "UserName"
  username = "telegraf_reader"
  password = "${OPCUA_PASSWORD}"    # From environment variable
  
  ## Subscription mode (server pushes changes to client)
  subscription_interval = "1s"
  
  ## Nodes to read
  [[inputs.opcua.nodes]]
    name = "temperature"
    namespace = "2"
    identifier_type = "s"
    identifier = "PLC1.Temperature"
  
  [[inputs.opcua.nodes]]
    name = "pressure"
    namespace = "2"
    identifier_type = "s"
    identifier = "PLC1.Pressure"
  
  [[inputs.opcua.nodes]]
    name = "humidity"
    namespace = "2"
    identifier_type = "s"
    identifier = "PLC1.Humidity"
  
  [[inputs.opcua.nodes]]
    name = "motor_rpm"
    namespace = "2"
    identifier_type = "s"
    identifier = "PLC1.MotorRPM"
  
  [[inputs.opcua.nodes]]
    name = "vibration"
    namespace = "2"
    identifier_type = "s"
    identifier = "PLC1.Vibration"
  
  [[inputs.opcua.nodes]]
    name = "power_kw"
    namespace = "2"
    identifier_type = "s"
    identifier = "PLC1.PowerKW"
```

### 2.4 Modbus TCP/RTU

For simpler sensors or legacy equipment that doesn't support OPC-UA.

#### Modbus Register Map (Typical Example)

| Register Address | Register Type | Data Type | Sensor | Unit | Scale Factor |
|-----------------|---------------|-----------|--------|------|-------------|
| 40001 | Holding Register | UINT16 | Temperature | °C | ÷ 10 |
| 40002 | Holding Register | UINT16 | Pressure | PSI | ÷ 10 |
| 40003 | Holding Register | UINT16 | Humidity | % | ÷ 10 |
| 40004–40005 | Holding Register | UINT32 | Motor RPM | RPM | × 1 |
| 40006 | Holding Register | UINT16 | Vibration | mm/s | ÷ 100 |
| 40007–40008 | Holding Register | FLOAT32 | Power | kW | × 1 |
| 10001 | Discrete Input | BOOL | Motor Running | — | — |
| 10002 | Discrete Input | BOOL | Emergency Stop | — | — |

> [!IMPORTANT]
> **Byte Order Matters!** Modbus uses Big-Endian byte order by default, but some PLCs use Little-Endian or Mid-Endian (byte-swapped). Always confirm the PLC's byte order configuration before reading multi-register values (UINT32, FLOAT32).

#### Telegraf Modbus Input Plugin (Production Config)

```toml
[[inputs.modbus]]
  ## Modbus TCP connection
  name = "production_line_1"
  slave_id = 1
  timeout = "3s"
  controller = "tcp://192.168.1.50:502"
  
  ## Holding registers (read/write)
  holding_registers = [
    { name = "temperature",  byte_order = "AB",   data_type = "UINT16",  scale = 0.1, address = [0] },
    { name = "pressure",     byte_order = "AB",   data_type = "UINT16",  scale = 0.1, address = [1] },
    { name = "humidity",     byte_order = "AB",   data_type = "UINT16",  scale = 0.1, address = [2] },
    { name = "motor_rpm",    byte_order = "ABCD", data_type = "UINT32",  scale = 1.0, address = [3, 4] },
    { name = "vibration",    byte_order = "AB",   data_type = "UINT16",  scale = 0.01, address = [5] },
    { name = "power_kw",     byte_order = "ABCD", data_type = "FLOAT32", scale = 1.0, address = [6, 7] },
  ]
  
  ## Discrete inputs (read-only, boolean)
  discrete_inputs = [
    { name = "motor_running",   address = [0] },
    { name = "emergency_stop",  address = [1] },
  ]
```

### 2.5 EtherNet/IP & PROFINET

| Protocol | Vendor Ecosystem | Port | How to Integrate |
|----------|-----------------|------|-----------------|
| **EtherNet/IP** | Allen-Bradley / Rockwell | 44818 (TCP), 2222 (UDP) | Use Telegraf `inputs.ether_ip` or Kepware gateway |
| **PROFINET** | Siemens | Layer 2 (no TCP port) | Use Siemens OPC-UA server or PROFINET-to-OPC-UA gateway |

> [!NOTE]
> For EtherNet/IP and PROFINET, the common production approach is to use a **protocol gateway** (like Kepware, Ignition, or the PLC's built-in OPC-UA server) to normalize everything to OPC-UA or MQTT, rather than reading these protocols directly.

---

## 3. Edge Gateway Architecture

In production, an **Edge Gateway** sits between the factory floor (OT network) and the monitoring stack (IT network). This is the most critical component for bridging the two worlds.

### What is an Edge Gateway?

```
  FACTORY FLOOR (OT Network)                    MONITORING STACK (IT Network)
  ─────────────────────────                      ────────────────────────────

  ┌────────┐  ┌────────┐                         ┌──────────┐
  │ PLC 1  │  │ PLC 2  │                         │ Mosquitto│
  │ S7-1500│  │ M580   │                         │ (MQTT    │
  └───┬────┘  └───┬────┘                         │  Broker) │
      │           │                               └─────▲────┘
      │ OPC-UA    │ Modbus TCP                          │
      │           │                                     │ MQTT/TLS
      ▼           ▼                                     │
  ┌───────────────────────────────────────┐             │
  │          EDGE GATEWAY                  │             │
  │                                        │             │
  │  ┌─────────────┐  ┌────────────────┐  │             │
  │  │ Protocol     │  │ Data           │  │    MQTT     │
  │  │ Drivers:     │  │ Processing:    │  │  Publish    │
  │  │ - OPC-UA     │  │ - Scaling      │──┼────────────►│
  │  │ - Modbus     │  │ - Filtering    │  │             │
  │  │ - S7comm     │  │ - Aggregation  │  │             │
  │  │ - EtherNet/IP│  │ - Dead-band    │  │             │
  │  └─────────────┘  │ - Store&Forward│  │             │
  │                    └────────────────┘  │             │
  │                                        │             │
  │  ┌─────────────────────────────────┐  │             │
  │  │ Local Buffer (SQLite / RocksDB) │  │             │
  │  │ Handles network outages         │  │             │
  │  └─────────────────────────────────┘  │             │
  │                                        │             │
  └───────────────────────────────────────┘             │
     Hardware: Industrial PC / Raspberry Pi              │
               or VM on plant server                     │
                                                         │
  ◄───────── DMZ / Firewall ──────────►                 │
```

### Edge Gateway Software Options

| Software | License | Protocols Supported | MQTT Output | Complexity |
|----------|---------|-------------------|-------------|------------|
| **Telegraf** | Open Source (MIT) | OPC-UA, Modbus, SNMP, MQTT | Yes | Low ⭐ |
| **Kepware KEPServerEX** | Commercial | 150+ protocols | Via IoT Gateway plugin | Medium |
| **Ignition Edge** | Commercial | OPC-UA, Modbus, Allen-Bradley | Via MQTT Transmission module | Medium |
| **Node-RED** | Open Source | Anything (via nodes) | Yes | Low |
| **AWS IoT Greengrass** | Commercial | Custom (Lambda) | AWS IoT Core | High |
| **Azure IoT Edge** | Commercial | Custom (Modules) | Azure IoT Hub | High |
| **Eclipse Kura** | Open Source | Modbus, OPC-UA, S7 | Yes | Medium |

> [!TIP]
> **For this project, Telegraf is the best fit** — it's already in the stack, supports OPC-UA and Modbus inputs natively, and can publish to MQTT. This eliminates the need for the separate Python simulator in production.

### Telegraf as Edge Gateway (Production Config)

```toml
# ═══════════════════════════════════════════════════════════════
# TELEGRAF EDGE GATEWAY CONFIGURATION
# Reads from PLCs, publishes to MQTT broker
# ═══════════════════════════════════════════════════════════════

[agent]
  interval = "5s"
  flush_interval = "5s"
  hostname = "edge-gateway-line1"

# ─── INPUT: OPC-UA from Siemens S7-1500 ───────────────────────
[[inputs.opcua]]
  name = "plc1"
  endpoint = "opc.tcp://192.168.10.100:4840"
  security_policy = "Basic256Sha256"
  security_mode = "SignAndEncrypt"
  certificate = "/etc/telegraf/certs/client.crt"
  private_key = "/etc/telegraf/certs/client.key"
  
  [[inputs.opcua.nodes]]
    name = "temperature"
    namespace = "2"
    identifier_type = "s"
    identifier = "PLC1.Temperature"
  
  # ... (more nodes)

# ─── INPUT: Modbus from Power Meter ───────────────────────────
[[inputs.modbus]]
  name = "power_meter_1"
  slave_id = 1
  controller = "tcp://192.168.10.50:502"
  
  holding_registers = [
    { name = "power_kw", byte_order = "ABCD", data_type = "FLOAT32", scale = 1.0, address = [0, 1] },
    { name = "voltage",  byte_order = "ABCD", data_type = "FLOAT32", scale = 1.0, address = [2, 3] },
    { name = "current",  byte_order = "ABCD", data_type = "FLOAT32", scale = 1.0, address = [4, 5] },
  ]

# ─── OUTPUT: MQTT Broker (with TLS) ──────────────────────────
[[outputs.mqtt]]
  servers = ["ssl://mqtt-broker.avgol.internal:8883"]
  topic = "factory/line1/{{ .PluginName }}"
  
  ## TLS Configuration
  tls_ca = "/etc/telegraf/certs/ca.crt"
  tls_cert = "/etc/telegraf/certs/client.crt"
  tls_key = "/etc/telegraf/certs/client.key"
  
  ## Authentication
  username = "edge-gateway-line1"
  password = "${MQTT_PASSWORD}"
  
  ## Data format
  data_format = "json"
  json_timestamp_units = "1ms"

# ─── OUTPUT: Also expose as Prometheus metrics ────────────────
[[outputs.prometheus_client]]
  listen = ":9273"
```

---

## 4. Data Formats in Production

### 4.1 Raw PLC Register Data

This is what lives inside the PLC memory before any protocol reads it:

```
PLC Memory Map (Siemens S7 example):
──────────────────────────────────────
DB1.DBD0   = 78.5    (REAL / FLOAT32)    → Temperature
DB1.DBD4   = 25.3    (REAL / FLOAT32)    → Pressure
DB1.DBW8   = 52      (INT / INT16)       → Humidity
DB1.DBD10  = 2100    (DINT / INT32)      → Motor RPM
DB1.DBD14  = 2.34    (REAL / FLOAT32)    → Vibration
DB1.DBD18  = 98.76   (REAL / FLOAT32)    → Power kW
DB1.DBX22.0 = true   (BOOL)             → Motor Running
DB1.DBX22.1 = false  (BOOL)             → Emergency Stop
```

### 4.2 OPC-UA Data Format

What an OPC-UA client receives when reading a node:

```json
{
    "NodeId": "ns=2;s=PLC1.Temperature",
    "DisplayName": "Temperature",
    "Value": {
        "Type": "Double",
        "Body": 78.5
    },
    "StatusCode": {
        "Code": 0,
        "Symbol": "Good"
    },
    "SourceTimestamp": "2026-06-14T07:30:00.123Z",
    "ServerTimestamp": "2026-06-14T07:30:00.125Z"
}
```

> [!NOTE]
> OPC-UA provides **data quality indicators** (`StatusCode`) which tell you if a sensor reading is reliable. Values like `Good`, `Bad_SensorFailure`, `Uncertain_LastUsableValue` are critical for production monitoring. The current simulator does not model this.

### 4.3 Modbus Data Format

Raw Modbus response (hexadecimal):

```
Request:  03 00 00 00 06        (Read Holding Registers, address 0, count 6)
Response: 03 0C 03 0D 00 FD 00 34 08 34 00 EA 00 63

Decoded:
  Register 40001 = 0x030D = 781  ÷ 10 = 78.1°C  (Temperature)
  Register 40002 = 0x00FD = 253  ÷ 10 = 25.3 PSI (Pressure)
  Register 40003 = 0x0034 = 52   ÷ 1  = 52%      (Humidity)
  Register 40004 = 0x0834 = 2100 × 1  = 2100 RPM (Motor RPM)
  Register 40005 = 0x00EA = 234  ÷ 100= 2.34mm/s (Vibration)
  Register 40006 = 0x0063 = 99   ÷ 1  = 99 kW    (Power)
```

### 4.4 MQTT Payload Standards (Sparkplug B)

For large-scale IIoT deployments, **Sparkplug B** is the industry-standard MQTT payload format:

```
Topic: spBv1.0/Avgol/DDATA/Line1/PLC1

Payload (Protocol Buffers - decoded):
{
    "timestamp": 1718358600123,
    "metrics": [
        {
            "name": "Temperature",
            "timestamp": 1718358600100,
            "dataType": "Double",
            "value": 78.5
        },
        {
            "name": "Pressure",
            "timestamp": 1718358600100,
            "dataType": "Double",
            "value": 25.3
        },
        {
            "name": "Motor/Running",
            "timestamp": 1718358600100,
            "dataType": "Boolean",
            "value": true
        }
    ],
    "seq": 42
}
```

**Sparkplug B Topic Namespace:**

```
spBv1.0/{group_id}/{message_type}/{edge_node_id}/{device_id}

Where:
  group_id      = "Avgol"       (organization)
  message_type  = NBIRTH / NDEATH / DBIRTH / DDEATH / DDATA / DCMD
  edge_node_id  = "Line1"       (edge gateway identifier)
  device_id     = "PLC1"        (specific PLC/device)
```

### 4.5 Unified JSON Schema for MQTT

If not using Sparkplug B, define a **consistent JSON schema** for all MQTT payloads:

```json
{
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Avgol IIoT Sensor Payload",
    "type": "object",
    "required": ["device_id", "timestamp", "metrics"],
    "properties": {
        "device_id": {
            "type": "string",
            "description": "Unique identifier for the PLC/device",
            "example": "plc1-line1"
        },
        "line": {
            "type": "string",
            "description": "Production line identifier",
            "example": "line1"
        },
        "plant": {
            "type": "string",
            "description": "Plant/facility identifier",
            "example": "avgol-india"
        },
        "timestamp": {
            "type": "string",
            "format": "date-time",
            "description": "ISO 8601 timestamp from source",
            "example": "2026-06-14T07:30:00.123Z"
        },
        "metrics": {
            "type": "object",
            "properties": {
                "temperature": { "type": "number", "unit": "celsius" },
                "pressure":    { "type": "number", "unit": "psi" },
                "humidity":    { "type": "number", "unit": "percent" },
                "motor_rpm":   { "type": "number", "unit": "rpm" },
                "vibration":   { "type": "number", "unit": "mm_per_s" },
                "power_kw":    { "type": "number", "unit": "kw" }
            }
        },
        "quality": {
            "type": "string",
            "enum": ["good", "uncertain", "bad"],
            "description": "OPC-UA quality indicator"
        }
    }
}
```

**Example payload conforming to this schema:**

```json
{
    "device_id": "plc1-line1",
    "line": "line1",
    "plant": "avgol-india",
    "timestamp": "2026-06-14T07:30:00.123Z",
    "metrics": {
        "temperature": 78.5,
        "pressure": 25.3,
        "humidity": 52,
        "motor_rpm": 2100,
        "vibration": 2.34,
        "power_kw": 98.76
    },
    "quality": "good"
}
```

---

## 5. Network Architecture & Connectivity

### 5.1 Purdue Model / ISA-95 Network Layers

Production IIoT networks follow the **Purdue Enterprise Reference Architecture** (ISA-95 standard):

```
┌──────────────────────────────────────────────────────────────────────┐
│ LEVEL 5: ENTERPRISE NETWORK (Corporate IT)                          │
│ ┌────────────────────────────────────────────────────────────────┐  │
│ │  ERP Systems, Business Intelligence, Cloud Services            │  │
│ │  Network: 10.0.0.0/8 (Corporate LAN / Internet)               │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│                         ┌────┴────┐                                 │
│                         │Firewall │                                 │
│                         └────┬────┘                                 │
│                              │                                      │
│ LEVEL 4: SITE BUSINESS NETWORK                                      │
│ ┌────────────────────────────────────────────────────────────────┐  │
│ │  Email, File Shares, Plant-level Business Systems              │  │
│ │  Network: 172.16.0.0/16                                        │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│                         ┌────┴────┐                                 │
│                         │Firewall │                                 │
│                         └────┬────┘                                 │
│                              │                                      │
│ LEVEL 3.5: DMZ (Demilitarized Zone)                                 │
│ ┌────────────────────────────────────────────────────────────────┐  │
│ │  ┌──────────┐  ┌────────────┐  ┌──────────┐  ┌────────────┐  │  │
│ │  │ Mosquitto│  │ Prometheus │  │ Grafana  │  │ Historian  │  │  │
│ │  │ (MQTT)   │  │ (TSDB)     │  │ (Viz)    │  │ (Optional) │  │  │
│ │  └──────────┘  └────────────┘  └──────────┘  └────────────┘  │  │
│ │  Network: 172.20.0.0/24 (IIoT DMZ)                            │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│                         ┌────┴────┐                                 │
│                         │Firewall │ ← Only MQTT (8883) allowed      │
│                         └────┬────┘                                 │
│                              │                                      │
│ LEVEL 3: SITE OPERATIONS (MES / SCADA Server)                       │
│ ┌────────────────────────────────────────────────────────────────┐  │
│ │  SCADA Servers, Historian, MES, Edge Gateways                  │  │
│ │  ┌──────────────┐                                              │  │
│ │  │ Edge Gateway │ ← Telegraf running here                      │  │
│ │  │ (Telegraf)   │                                              │  │
│ │  └──────────────┘                                              │  │
│ │  Network: 192.168.10.0/24 (OT Server VLAN)                    │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│                         ┌────┴────┐                                 │
│                         │Firewall │ ← OPC-UA (4840), Modbus (502)   │
│                         └────┬────┘                                 │
│                              │                                      │
│ LEVEL 2: AREA SUPERVISORY CONTROL                                   │
│ ┌────────────────────────────────────────────────────────────────┐  │
│ │  HMIs, Engineering Workstations, SCADA Clients                 │  │
│ │  Network: 192.168.20.0/24 (Control VLAN)                       │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│ LEVEL 1: BASIC CONTROL (PLC / DCS / RTU)                            │
│ ┌────────────────────────────────────────────────────────────────┐  │
│ │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐           │  │
│ │  │PLC 1 │  │PLC 2 │  │PLC 3 │  │VFD 1 │  │VFD 2 │           │  │
│ │  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘           │  │
│ │  Network: 192.168.30.0/24 (Control Network VLAN)               │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│ LEVEL 0: PHYSICAL PROCESS (Sensors / Actuators)                     │
│ ┌────────────────────────────────────────────────────────────────┐  │
│ │  Temperature sensors, Pressure gauges, Motors, Valves          │  │
│ │  Connection: 4-20mA / 0-10V / RS-485 / Direct I/O             │  │
│ └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.2 Port Reference Table

| Port | Protocol | Direction | Service | Network Layer | TLS? |
|------|----------|-----------|---------|---------------|------|
| **502** | Modbus TCP | Edge GW → PLC | PLC Modbus Server | L1 → L3 | No (use VPN) |
| **4840** | OPC-UA | Edge GW → PLC | PLC OPC-UA Server | L1 → L3 | Yes (built-in) |
| **44818** | EtherNet/IP | Edge GW → PLC | Allen-Bradley PLC | L1 → L3 | No |
| **102** | S7comm | Edge GW → PLC | Siemens S7 (legacy) | L1 → L3 | No |
| **1883** | MQTT | Internal only | Mosquitto (plain) | L3 internal | No |
| **8883** | MQTTS | Edge GW → Broker | Mosquitto (TLS) | L3 → DMZ | **Yes** |
| **8084** | MQTT/WSS | Web clients → Broker | Mosquitto WebSocket | DMZ → L4 | **Yes** |
| **9273** | HTTP | Prometheus → Telegraf | Telegraf metrics | DMZ internal | Optional |
| **9090** | HTTP | Grafana → Prometheus | Prometheus API | DMZ internal | Optional |
| **3000** | HTTPS | Users → Grafana | Grafana Web UI | DMZ → L4 | **Yes** |
| **443** | HTTPS | Reverse Proxy | Nginx / Traefik | DMZ → L4 | **Yes** |

### 5.3 Firewall Rules

#### Firewall between Level 1 (PLCs) and Level 3 (Edge Gateway)

| Rule | Source | Destination | Port | Protocol | Action |
|------|--------|-------------|------|----------|--------|
| 1 | Edge Gateway (192.168.10.x) | PLCs (192.168.30.0/24) | 4840 | TCP (OPC-UA) | **ALLOW** |
| 2 | Edge Gateway (192.168.10.x) | PLCs (192.168.30.0/24) | 502 | TCP (Modbus) | **ALLOW** |
| 3 | Any | PLCs (192.168.30.0/24) | * | * | **DENY** |

#### Firewall between Level 3 (Edge Gateway) and DMZ

| Rule | Source | Destination | Port | Protocol | Action |
|------|--------|-------------|------|----------|--------|
| 1 | Edge Gateway (192.168.10.x) | MQTT Broker (172.20.0.x) | 8883 | TCP (MQTTS) | **ALLOW** |
| 2 | Prometheus (172.20.0.x) | Telegraf (172.20.0.x) | 9273 | TCP (HTTP) | **ALLOW** |
| 3 | Grafana (172.20.0.x) | Prometheus (172.20.0.x) | 9090 | TCP (HTTP) | **ALLOW** |
| 4 | Any | DMZ (172.20.0.0/24) | * | * | **DENY** |

#### Firewall between DMZ and Corporate Network

| Rule | Source | Destination | Port | Protocol | Action |
|------|--------|-------------|------|----------|--------|
| 1 | Corporate Users (10.0.0.0/8) | Grafana (172.20.0.x) | 443 | TCP (HTTPS) | **ALLOW** |
| 2 | Any | DMZ (172.20.0.0/24) | * | * | **DENY** |

### 5.4 Network Segmentation

```
VLAN 10:  Control Network     (192.168.30.0/24)  — PLCs, HMIs
VLAN 20:  OT Server Network   (192.168.10.0/24)  — Edge Gateways, SCADA
VLAN 30:  IIoT DMZ            (172.20.0.0/24)    — MQTT, Prometheus, Grafana
VLAN 40:  Corporate IT        (10.0.0.0/8)       — Users, ERP
```

---

## 6. Production Architecture

### 6.1 Single-Site Deployment

```
  ┌─────────────── FACTORY FLOOR ───────────────────────────────────┐
  │                                                                  │
  │  Production Line 1              Production Line 2                │
  │  ┌────┐ ┌────┐ ┌────┐          ┌────┐ ┌────┐ ┌────┐           │
  │  │PLC1│ │PLC2│ │PLC3│          │PLC4│ │PLC5│ │PLC6│           │
  │  └──┬─┘ └──┬─┘ └──┬─┘          └──┬─┘ └──┬─┘ └──┬─┘           │
  │     │      │      │                │      │      │              │
  │     └──────┼──────┘                └──────┼──────┘              │
  │            │ OPC-UA / Modbus              │ OPC-UA / Modbus     │
  │            ▼                              ▼                      │
  │     ┌──────────────┐              ┌──────────────┐              │
  │     │ Edge Gateway │              │ Edge Gateway │              │
  │     │ (Telegraf)   │              │ (Telegraf)   │              │
  │     │ Line 1       │              │ Line 2       │              │
  │     └──────┬───────┘              └──────┬───────┘              │
  │            │ MQTT/TLS (8883)             │ MQTT/TLS (8883)      │
  └────────────┼─────────────────────────────┼──────────────────────┘
               │                             │
               ▼                             ▼
  ┌─────────── SERVER ROOM (DMZ) ──────────────────────────────────┐
  │                                                                  │
  │  ┌───────────────────────────────────────────────────┐          │
  │  │              MQTT BROKER (Mosquitto/EMQX)         │          │
  │  │              Port: 8883 (TLS)                     │          │
  │  │              Topics: factory/line1/+, factory/line2/+│       │
  │  └───────────────────────┬───────────────────────────┘          │
  │                          │                                       │
  │  ┌───────────────────────▼───────────────────────────┐          │
  │  │              TELEGRAF (Metrics Bridge)             │          │
  │  │              Subscribe: factory/#                  │          │
  │  │              Expose: :9273/metrics                 │          │
  │  └───────────────────────┬───────────────────────────┘          │
  │                          │                                       │
  │  ┌───────────────────────▼───────────────────────────┐          │
  │  │              PROMETHEUS (TSDB)                     │          │
  │  │              Scrape: telegraf:9273 every 5s        │          │
  │  │              Retention: 90 days                    │          │
  │  │              Storage: /data/prometheus (SSD)       │          │
  │  └───────────────────────┬───────────────────────────┘          │
  │                          │                                       │
  │  ┌───────────────────────▼───────────────────────────┐          │
  │  │              GRAFANA (Dashboard)                   │          │
  │  │              Port: 443 (via Nginx reverse proxy)   │          │
  │  │              Auth: LDAP / Active Directory         │          │
  │  └──────────────────────────────────────────────────┘          │
  │                                                                  │
  └──────────────────────────────────────────────────────────────────┘
               │
               │ HTTPS (443)
               ▼
  ┌─────────── CORPORATE NETWORK ──────────────────────────────────┐
  │  Plant Manager Dashboard (Browser)                               │
  │  Engineering Workstations                                        │
  │  Mobile Devices                                                  │
  └──────────────────────────────────────────────────────────────────┘
```

### 6.2 Multi-Site / Cloud Deployment

```
  ┌── Plant A (India) ──┐    ┌── Plant B (Israel) ──┐    ┌── Plant C (USA) ──┐
  │ Edge GW → Local MQTT│    │ Edge GW → Local MQTT │    │ Edge GW → Local MQTT│
  └─────────┬───────────┘    └─────────┬────────────┘    └─────────┬──────────┘
            │                          │                           │
            │   MQTT Bridge / VPN      │    MQTT Bridge / VPN      │
            │                          │                           │
            ▼                          ▼                           ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │                     CLOUD / CENTRAL DATA CENTER                          │
  │                                                                          │
  │  ┌──────────────────┐  ┌──────────────┐  ┌───────────────────────────┐  │
  │  │ EMQX Cluster     │  │ Prometheus   │  │ Grafana                   │  │
  │  │ (MQTT Broker)    │──│ + Thanos     │──│ Multi-tenant dashboards   │  │
  │  │ HA: 3 nodes      │  │ Long-term    │  │ per-plant views           │  │
  │  └──────────────────┘  │ storage (S3) │  └───────────────────────────┘  │
  │                        └──────────────┘                                  │
  └──────────────────────────────────────────────────────────────────────────┘
```

---

## 7. How Data Will Be Received in Production

### 7.1 Scenario A: Direct PLC → MQTT

**When to use**: Modern PLCs with built-in MQTT client (e.g., Siemens S7-1500 with CP 1545-1)

```
PLC (S7-1500)  ──── MQTT Publish ────►  Mosquitto Broker
                    Port 8883 (TLS)
                    Topic: factory/line1/plc1
```

**PLC Configuration** (in TIA Portal / PLC programming software):
- Configure MQTT client block in PLC program
- Set broker address, port, TLS certificates
- Map PLC data blocks to JSON payload
- Set publish interval (e.g., every 1–5 seconds)

> [!NOTE]
> Very few PLCs support native MQTT. This scenario applies mainly to Siemens S7-1500 with the MQTT library, Beckhoff TwinCAT with TF6701, or custom PLC programs using MQTT function blocks.

### 7.2 Scenario B: PLC → Edge Gateway → MQTT

**When to use**: Most common production scenario. PLCs communicate via their native protocols, and an edge gateway translates to MQTT.

```
PLC 1 (OPC-UA, port 4840)  ──┐
PLC 2 (Modbus, port 502)   ──┼──►  Edge Gateway  ──── MQTT ────►  Broker
PLC 3 (S7comm, port 102)   ──┘     (Telegraf)         Port 8883
```

**Data Reception Flow**:

```
1. Edge Gateway polls PLC via OPC-UA (subscription mode, 1s interval)
2. PLC responds with current values + timestamps + quality codes
3. Edge Gateway:
   a. Validates data quality (discard "Bad" quality readings)
   b. Applies deadband filtering (only send if value changed > threshold)
   c. Adds metadata (device_id, line, plant, timestamp)
   d. Serializes to JSON
   e. Publishes to MQTT topic
4. MQTT Broker receives and routes to subscribers (Telegraf)
```

### 7.3 Scenario C: PLC → OPC-UA Server → Telegraf → MQTT

**When to use**: When using a standalone OPC-UA server (like Kepware) as a protocol aggregator.

```
PLC 1 (Any protocol)  ──┐
PLC 2 (Any protocol)  ──┼──►  Kepware  ──── OPC-UA ────►  Telegraf  ── MQTT ──►  Broker
PLC 3 (Any protocol)  ──┘     (OPC-UA     Port 49320                    8883
Sensor (4-20mA)        ──┘     Server)
```

**Kepware Configuration**:

| Setting | Value |
|---------|-------|
| **OPC-UA Endpoint** | `opc.tcp://kepware-server:49320` |
| **Channels** | One per PLC/device |
| **Devices** | One per physical PLC |
| **Tags** | One per sensor reading |
| **Scan Rate** | 1000 ms |
| **Security** | Basic256Sha256, SignAndEncrypt |

### 7.4 Scenario D: Legacy Analog Sensors → IoT Gateway → MQTT

**When to use**: Brownfield installations with no PLC, just raw analog sensors.

```
4-20mA Temperature Sensor  ──┐
0-10V Pressure Sensor       ──┼──►  IoT Gateway  ──── MQTT ────►  Broker
RTD (PT100)                  ──┘     (e.g., Moxa         8883
Digital I/O                  ──┘      ioThinx 4510)
```

**IoT Gateway converts**:
- 4-20mA → Engineering units (e.g., 4mA = 0°C, 20mA = 100°C)
- 0-10V → Engineering units (e.g., 0V = 0 PSI, 10V = 50 PSI)
- RTD resistance → Temperature (°C/°F)
- Digital I/O → Boolean (0/1)

**Common IoT Gateway Hardware**:

| Vendor | Model | Inputs | Protocols Out | Price Range |
|--------|-------|--------|--------------|-------------|
| **Moxa** | ioThinx 4510 | 8 AI, 4 DI, 4 DO | MQTT, Modbus | $300–500 |
| **Advantech** | WISE-4012 | 4 AI, 4 DI | MQTT, RESTful | $200–400 |
| **Siemens** | IOT2050 | Configurable | MQTT, OPC-UA | $300–500 |
| **Raspberry Pi** | + HAT module | 8 AI, 8 DI | MQTT (custom) | $100–200 |
| **Phoenix Contact** | AXC F 2152 | Modular | MQTT, OPC-UA | $500–800 |

---

## 8. MQTT Topic Design for Production

### Topic Hierarchy

```
{company}/{plant}/{area}/{line}/{device_type}/{device_id}/{data_type}
```

### Full Topic Structure

```
avgol/
├── india/
│   ├── production/
│   │   ├── line1/
│   │   │   ├── plc/
│   │   │   │   ├── plc1/
│   │   │   │   │   ├── telemetry        ← Sensor data (every 5s)
│   │   │   │   │   ├── status           ← PLC status (online/offline/fault)
│   │   │   │   │   ├── alarms           ← Active alarm conditions
│   │   │   │   │   └── config           ← Configuration changes
│   │   │   │   └── plc2/
│   │   │   │       ├── telemetry
│   │   │   │       └── ...
│   │   │   ├── sensor/
│   │   │   │   ├── temp-001/telemetry
│   │   │   │   └── vibration-001/telemetry
│   │   │   └── drive/
│   │   │       ├── vfd-001/telemetry
│   │   │       └── vfd-002/telemetry
│   │   └── line2/
│   │       └── ...
│   ├── utilities/
│   │   ├── hvac/
│   │   │   └── ahu-001/telemetry
│   │   ├── compressor/
│   │   │   └── comp-001/telemetry
│   │   └── power/
│   │       └── meter-001/telemetry
│   └── warehouse/
│       └── ...
├── israel/
│   └── ...
└── usa/
    └── ...
```

### Subscription Patterns (Wildcards)

| Subscriber | Topic Pattern | What It Receives |
|------------|--------------|-----------------|
| All data from Line 1 | `avgol/india/production/line1/#` | Everything from Line 1 |
| All telemetry from all PLCs | `avgol/india/production/+/plc/+/telemetry` | Sensor data from all PLCs |
| All alarms from entire plant | `avgol/india/+/+/+/+/alarms` | All alarm events |
| Single PLC | `avgol/india/production/line1/plc/plc1/telemetry` | One specific PLC |
| All plants (cloud) | `avgol/#` | Everything from all facilities |

### MQTT QoS Levels for Production

| Data Type | QoS Level | Rationale |
|-----------|-----------|-----------|
| Telemetry (periodic sensor data) | **QoS 0** (At most once) | Acceptable to lose a sample — next one comes in 5s |
| Alarms & Events | **QoS 1** (At least once) | Must be delivered, duplicates OK |
| Configuration Commands | **QoS 2** (Exactly once) | Critical — must arrive exactly once |
| Device Birth/Death | **QoS 1** (At least once) | Must track device connectivity |

---

## 9. Security Requirements

### 9.1 MQTT Broker Security (Mosquitto)

**Production `mosquitto.conf`**:

```conf
# ═══════════════════════════════════════════════════════
# PRODUCTION MOSQUITTO CONFIGURATION
# ═══════════════════════════════════════════════════════

# ─── Listener: TLS-only ──────────────────────────────
listener 8883
protocol mqtt

# ─── TLS Configuration ──────────────────────────────
cafile /mosquitto/certs/ca.crt
certfile /mosquitto/certs/server.crt
keyfile /mosquitto/certs/server.key
tls_version tlsv1.3
require_certificate true                    # Mutual TLS (mTLS)

# ─── Authentication ─────────────────────────────────
allow_anonymous false
password_file /mosquitto/config/passwords   # Hashed passwords
acl_file /mosquitto/config/acl              # Topic-level access control

# ─── WebSocket Listener (for web dashboards) ────────
listener 8084
protocol websockets
cafile /mosquitto/certs/ca.crt
certfile /mosquitto/certs/server.crt
keyfile /mosquitto/certs/server.key

# ─── Connection limits ──────────────────────────────
max_connections 1000
max_inflight_messages 20
max_queued_messages 5000
message_size_limit 1048576                  # 1 MB max message

# ─── Logging ────────────────────────────────────────
log_type all
log_dest file /mosquitto/log/mosquitto.log
log_timestamp true
log_timestamp_format %Y-%m-%dT%H:%M:%S

# ─── Persistence ────────────────────────────────────
persistence true
persistence_location /mosquitto/data/
autosave_interval 60
```

**Access Control List (ACL) file**:

```
# Edge Gateway Line 1 — can publish to line1 topics only
user edge-gateway-line1
topic write avgol/india/production/line1/#
topic read avgol/india/production/line1/+/+/config

# Edge Gateway Line 2
user edge-gateway-line2
topic write avgol/india/production/line2/#

# Telegraf (metrics bridge) — read-only access to all telemetry
user telegraf-reader
topic read avgol/#

# Grafana Live — read-only
user grafana
topic read avgol/#

# Admin — full access
user admin
topic readwrite #
```

### 9.2 TLS/SSL Certificates

**Certificate chain for production**:

```
Root CA (self-signed or enterprise PKI)
├── Server Certificate (mosquitto broker)
├── Client Certificate (edge-gateway-line1)
├── Client Certificate (edge-gateway-line2)
├── Client Certificate (telegraf-reader)
└── Client Certificate (grafana)
```

**Generate certificates using OpenSSL** (reference commands):

```bash
# 1. Generate CA private key and certificate
openssl genrsa -out ca.key 4096
openssl req -x509 -new -key ca.key -sha256 -days 3650 -out ca.crt \
    -subj "/C=IN/ST=Gujarat/O=Avgol/CN=Avgol-IIoT-CA"

# 2. Generate server certificate for Mosquitto
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr \
    -subj "/C=IN/ST=Gujarat/O=Avgol/CN=mqtt-broker.avgol.internal"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out server.crt -days 365 -sha256

# 3. Generate client certificate for Edge Gateway
openssl genrsa -out client-edge-line1.key 2048
openssl req -new -key client-edge-line1.key -out client-edge-line1.csr \
    -subj "/C=IN/ST=Gujarat/O=Avgol/CN=edge-gateway-line1"
openssl x509 -req -in client-edge-line1.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out client-edge-line1.crt -days 365 -sha256
```

### 9.3 Network Security

| Measure | Implementation |
|---------|---------------|
| **VLAN Segmentation** | Separate VLANs for OT (PLCs), Edge, DMZ, IT |
| **Firewall Rules** | Allowlist-only between zones (see Section 5.3) |
| **VPN** | Site-to-site VPN for multi-plant connectivity |
| **Network Monitoring** | IDS/IPS on OT/IT boundary (e.g., Claroty, Nozomi) |
| **No Internet Access** | OT network has zero internet connectivity |
| **Jump Server** | Remote access only through hardened bastion host |
| **802.1X** | Port-based network authentication for all devices |

### 9.4 Grafana Security

```ini
# grafana.ini — Production security settings

[server]
protocol = https
cert_file = /etc/grafana/certs/grafana.crt
cert_key = /etc/grafana/certs/grafana.key
domain = grafana.avgol.internal

[security]
admin_user = admin
admin_password = ${GF_ADMIN_PASSWORD}    # From secrets manager
secret_key = ${GF_SECRET_KEY}            # For signing cookies
cookie_secure = true
cookie_samesite = strict
disable_gravatar = true
disable_brute_force_login_protection = false

[auth]
disable_login_form = true                # Force SSO

[auth.ldap]
enabled = true
config_file = /etc/grafana/ldap.toml     # Active Directory integration

[users]
allow_sign_up = false
auto_assign_org = true
auto_assign_org_role = Viewer
```

### 9.5 Prometheus Security

```yaml
# prometheus.yml — Production configuration
global:
  scrape_interval: 5s
  evaluation_interval: 5s

# Basic auth for Prometheus (via reverse proxy)
# Prometheus itself doesn't support auth natively
# Use Nginx/Traefik as reverse proxy with auth

scrape_configs:
  - job_name: telegraf
    scheme: https
    tls_config:
      ca_file: /etc/prometheus/certs/ca.crt
      cert_file: /etc/prometheus/certs/client.crt
      key_file: /etc/prometheus/certs/client.key
    static_configs:
      - targets:
          - telegraf:9273

  # Self-monitoring
  - job_name: prometheus
    static_configs:
      - targets:
          - localhost:9090

# Recording rules for performance
rule_files:
  - /etc/prometheus/rules/*.yml

# Alerting configuration
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093
```

---

## 10. Data Persistence & Retention

### Storage Strategy

| Data Age | Storage Tier | Resolution | Tool |
|----------|-------------|-----------|------|
| 0 – 15 days | Hot (SSD, local) | Full resolution (5s) | Prometheus |
| 15 – 90 days | Warm (HDD, local) | Downsampled (1 min) | Thanos Compact |
| 90 days – 2 years | Cold (Object Storage) | Downsampled (5 min) | Thanos + S3/MinIO |
| 2+ years | Archive | Downsampled (1 hour) | S3 Glacier / Tape |

### Prometheus Storage Configuration

```yaml
# prometheus.yml command-line flags
# Run with: prometheus --config.file=prometheus.yml \
#   --storage.tsdb.path=/data/prometheus \
#   --storage.tsdb.retention.time=15d \
#   --storage.tsdb.retention.size=50GB \
#   --storage.tsdb.wal-compression
```

### Disk Space Estimation

```
Per metric point:     ~1-2 bytes (Prometheus TSDB compression)
Metrics per PLC:      6 sensors
PLCs:                 20 (example)
Samples per day:      17,280 (every 5s × 86,400s/day)

Daily storage:
  = 20 PLCs × 6 metrics × 17,280 samples × 2 bytes
  = ~4.15 MB/day
  = ~125 MB/month
  = ~1.5 GB/year

With 50 PLCs and 20 metrics each:
  = 50 × 20 × 17,280 × 2 = ~34.5 MB/day = ~1 GB/month = ~12.5 GB/year
```

---

## 11. High Availability & Redundancy

### MQTT Broker HA

```
                    Load Balancer
                    (HAProxy / Nginx)
                    Port: 8883
                         │
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
     ┌──────────┐  ┌──────────┐  ┌──────────┐
     │ EMQX     │  │ EMQX     │  │ EMQX     │
     │ Node 1   │──│ Node 2   │──│ Node 3   │
     │ (Active) │  │ (Active) │  │ (Active) │
     └──────────┘  └──────────┘  └──────────┘
          │              │              │
          └──────────────┼──────────────┘
                    Cluster Bus
                    (Erlang Distribution)
```

> [!IMPORTANT]
> For production HA, consider replacing Mosquitto with **EMQX** or **HiveMQ**, which support native clustering. Mosquitto is single-instance only — it has a bridge mode but not true clustering.

### Prometheus HA

```
     ┌──────────────┐      ┌──────────────┐
     │ Prometheus A │      │ Prometheus B │    ← Both scrape same targets
     │ (Primary)    │      │ (Replica)    │
     └──────┬───────┘      └──────┬───────┘
            │                     │
            └──────────┬──────────┘
                       ▼
              ┌──────────────┐
              │ Thanos Query │    ← Deduplicates & merges
              │ (Frontend)   │
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │ Grafana      │
              └──────────────┘
```

### Grafana HA

| Component | HA Strategy |
|-----------|------------|
| Grafana instances | 2+ behind load balancer |
| Session storage | PostgreSQL or MySQL (shared DB) |
| Dashboard storage | Git-based provisioning (version controlled) |

---

## 12. Alerting & Notifications

### Alert Rules (Prometheus / Grafana)

```yaml
# /etc/prometheus/rules/factory_alerts.yml

groups:
  - name: factory_alerts
    rules:
      # ─── Temperature Alerts ───────────────────────────
      - alert: HighTemperature
        expr: mqtt_consumer_temperature > 85
        for: 2m
        labels:
          severity: warning
          area: production
        annotations:
          summary: "High temperature detected on {{ $labels.instance }}"
          description: "Temperature is {{ $value }}°C (threshold: 85°C) for more than 2 minutes."

      - alert: CriticalTemperature
        expr: mqtt_consumer_temperature > 95
        for: 30s
        labels:
          severity: critical
          area: production
        annotations:
          summary: "CRITICAL: Temperature {{ $value }}°C on {{ $labels.instance }}"
          description: "Immediate action required. Temperature exceeds safe operating limit."

      # ─── Motor Alerts ──────────────────────────────────
      - alert: MotorOverspeed
        expr: mqtt_consumer_motor_rpm > 2800
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Motor overspeed: {{ $value }} RPM on {{ $labels.instance }}"

      # ─── Data Freshness ────────────────────────────────
      - alert: SensorDataStale
        expr: time() - mqtt_consumer_temperature_timestamp > 30
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "No data received from sensor for 30+ seconds"

      # ─── Vibration Anomaly ─────────────────────────────
      - alert: ExcessiveVibration
        expr: mqtt_consumer_vibration > 4.0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Excessive vibration: {{ $value }} mm/s"
          description: "May indicate bearing failure or misalignment."
```

### Notification Channels

| Channel | Use Case | Tool |
|---------|---------|------|
| **Email** | Shift supervisors, management reports | Grafana Alerting / Alertmanager |
| **SMS** | Critical alarms (plant shutdown risk) | Twilio / Alertmanager webhook |
| **Slack / Teams** | Engineering team notifications | Grafana Alerting integration |
| **PagerDuty** | On-call escalation for critical events | Alertmanager → PagerDuty |
| **WhatsApp** | Local teams (common in India/Israel) | Custom webhook → WhatsApp API |
| **Plant PA System** | Audible alarms on factory floor | Custom integration |
| **HMI Pop-up** | Operator display at machine | SCADA/HMI integration |

---

## 13. Scaling Considerations

### Capacity Planning

| Scale | PLCs | Metrics/sec | MQTT Msgs/sec | Prometheus RAM | Disk/Month |
|-------|------|-------------|---------------|---------------|------------|
| **Small** (1 line) | 5 | 6 | 1 | 512 MB | 50 MB |
| **Medium** (5 lines) | 25 | 30 | 5 | 1 GB | 250 MB |
| **Large** (full plant) | 100 | 200 | 20 | 4 GB | 1 GB |
| **Enterprise** (multi-plant) | 500+ | 2000+ | 100+ | 16 GB+ | 5 GB+ |

### When to Scale What

| Bottleneck | Symptom | Solution |
|-----------|---------|---------|
| MQTT Broker overloaded | Message delivery delay > 1s | Switch to EMQX cluster (3 nodes) |
| Telegraf can't keep up | `/metrics` endpoint slow | Run multiple Telegraf instances, partition by topic |
| Prometheus slow queries | Dashboard takes > 5s to load | Add recording rules, increase RAM, use Thanos |
| Prometheus disk full | `storage retention` errors | Add persistent volume, enable Thanos for offloading |
| Grafana slow | Dashboard unresponsive | Multiple instances behind load balancer, PostgreSQL backend |

---

## 14. Production Docker Compose (Reference)

```yaml
# docker-compose.production.yml
# ═══════════════════════════════════════════════════════════════
# PRODUCTION DEPLOYMENT — DO NOT USE docker-compose.yml (dev)
# ═══════════════════════════════════════════════════════════════

version: '3.8'

services:

  # ─── MQTT Broker ────────────────────────────────────────────
  mosquitto:
    image: eclipse-mosquitto:2
    container_name: mosquitto
    restart: always
    ports:
      - "8883:8883"           # MQTT over TLS only
      - "8084:8084"           # WebSocket over TLS
      # NOTE: Port 1883 NOT exposed (no plaintext MQTT)
    volumes:
      - ./mosquitto/mosquitto-prod.conf:/mosquitto/config/mosquitto.conf:ro
      - ./mosquitto/passwords:/mosquitto/config/passwords:ro
      - ./mosquitto/acl:/mosquitto/config/acl:ro
      - ./certs/ca.crt:/mosquitto/certs/ca.crt:ro
      - ./certs/server.crt:/mosquitto/certs/server.crt:ro
      - ./certs/server.key:/mosquitto/certs/server.key:ro
      - mosquitto_data:/mosquitto/data
      - mosquitto_log:/mosquitto/log
    networks:
      - iiot_dmz
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '1.0'
    healthcheck:
      test: ["CMD", "mosquitto_sub", "-t", "$$SYS/#", "-C", "1", "-i", "healthcheck", "-W", "3"]
      interval: 30s
      timeout: 10s
      retries: 3

  # ─── Telegraf (MQTT → Prometheus bridge) ────────────────────
  telegraf:
    image: telegraf:1.31
    container_name: telegraf
    restart: always
    ports:
      - "9273:9273"           # Prometheus metrics endpoint
    volumes:
      - ./telegraf/telegraf-prod.conf:/etc/telegraf/telegraf.conf:ro
      - ./certs:/etc/telegraf/certs:ro
    networks:
      - iiot_dmz
    depends_on:
      mosquitto:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.5'

  # ─── Prometheus (Time-Series Database) ──────────────────────
  prometheus:
    image: prom/prometheus:v2.53.0
    container_name: prometheus
    restart: always
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=15d'
      - '--storage.tsdb.retention.size=50GB'
      - '--storage.tsdb.wal-compression'
      - '--web.enable-lifecycle'
    volumes:
      - ./prometheus/prometheus-prod.yml:/etc/prometheus/prometheus.yml:ro
      - ./prometheus/rules:/etc/prometheus/rules:ro
      - ./certs:/etc/prometheus/certs:ro
      - prometheus_data:/prometheus
    networks:
      - iiot_dmz
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2.0'
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:9090/-/healthy"]
      interval: 30s
      timeout: 10s
      retries: 3

  # ─── Alertmanager ───────────────────────────────────────────
  alertmanager:
    image: prom/alertmanager:v0.27.0
    container_name: alertmanager
    restart: always
    ports:
      - "9093:9093"
    volumes:
      - ./alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
    networks:
      - iiot_dmz

  # ─── Grafana (Dashboard & Visualization) ────────────────────
  grafana:
    image: grafana/grafana:11.1.0
    container_name: grafana
    restart: always
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: ${GF_ADMIN_PASSWORD}       # From .env file
      GF_SECURITY_SECRET_KEY: ${GF_SECRET_KEY}
      GF_SERVER_PROTOCOL: https
      GF_SERVER_CERT_FILE: /etc/grafana/certs/grafana.crt
      GF_SERVER_CERT_KEY: /etc/grafana/certs/grafana.key
      GF_SERVER_DOMAIN: grafana.avgol.internal
      GF_AUTH_DISABLE_LOGIN_FORM: "false"
      GF_USERS_ALLOW_SIGN_UP: "false"
      GF_DATABASE_TYPE: postgres
      GF_DATABASE_HOST: ${POSTGRES_HOST}
      GF_DATABASE_NAME: grafana
      GF_DATABASE_USER: grafana
      GF_DATABASE_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
      - ./certs:/etc/grafana/certs:ro
    networks:
      - iiot_dmz
    depends_on:
      prometheus:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'

  # ─── Nginx Reverse Proxy ───────────────────────────────────
  nginx:
    image: nginx:alpine
    container_name: nginx-proxy
    restart: always
    ports:
      - "443:443"             # HTTPS only
      - "80:80"               # Redirect to HTTPS
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
    networks:
      - iiot_dmz
    depends_on:
      - grafana

volumes:
  mosquitto_data:
  mosquitto_log:
  prometheus_data:

networks:
  iiot_dmz:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/24
```

---

## 15. Production Deployment Checklist

### Pre-Deployment

- [ ] **Network**: VLANs configured and tested (OT, Edge, DMZ, IT)
- [ ] **Firewall**: Rules applied per Section 5.3
- [ ] **Certificates**: CA, server, and client TLS certs generated and distributed
- [ ] **DNS**: Internal DNS entries for `mqtt-broker.avgol.internal`, `grafana.avgol.internal`
- [ ] **PLC Access**: OPC-UA server enabled on PLCs, firewall allows port 4840
- [ ] **PLC Tags**: Complete tag list with data types, ranges, and engineering units
- [ ] **Modbus Map**: Register addresses verified with PLC vendor documentation
- [ ] **Edge Gateway**: Telegraf installed and configured on industrial PC
- [ ] **Storage**: Persistent volumes provisioned (SSD for Prometheus, HDD for archive)
- [ ] **Backup**: Grafana DB backup strategy defined
- [ ] **Credentials**: All passwords stored in secrets manager (not plaintext)

### Deployment

- [ ] Deploy MQTT broker with TLS and ACLs
- [ ] Deploy Telegraf bridge (subscriber side)
- [ ] Deploy Prometheus with retention and alerting rules
- [ ] Deploy Alertmanager with notification channels
- [ ] Deploy Grafana with LDAP/SSO and provisioned dashboards
- [ ] Deploy Nginx reverse proxy with HTTPS
- [ ] Configure and start edge gateways on factory floor
- [ ] Verify end-to-end data flow from PLC to dashboard

### Post-Deployment

- [ ] **Monitoring**: Prometheus self-monitoring + Grafana health dashboard
- [ ] **Alerting**: Test all alert rules and notification channels
- [ ] **Documentation**: Update runbooks with production-specific procedures
- [ ] **Training**: Operators trained on Grafana dashboards
- [ ] **DR Plan**: Disaster recovery and failover procedures documented
- [ ] **Audit**: Security audit of all components
- [ ] **Performance**: Baseline metrics recorded (latency, throughput)

---

## 16. Hardware Requirements

### Edge Gateway Server (Per Production Line)

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 2 cores (x86_64 or ARM64) | 4 cores |
| **RAM** | 2 GB | 4 GB |
| **Storage** | 32 GB SSD | 64 GB SSD |
| **Network** | 1× GbE (OT) + 1× GbE (IT) | Dual NIC mandatory |
| **OS** | Ubuntu 22.04 LTS / Debian 12 | Same |
| **Form Factor** | DIN-rail industrial PC | Siemens IPC227E, Advantech UNO-2484G |
| **Power** | 12–24V DC, 30W | Redundant PSU |
| **Environment** | 0–50°C, fanless | Industrial-rated IP20 or IP54 |

### Central Server (DMZ — Monitoring Stack)

| Component | Minimum | Recommended (100+ PLCs) |
|-----------|---------|------------------------|
| **CPU** | 4 cores | 8 cores |
| **RAM** | 8 GB | 16–32 GB |
| **Storage (Prometheus)** | 100 GB SSD | 500 GB NVMe SSD |
| **Storage (Grafana)** | 20 GB | 50 GB SSD |
| **Network** | 1 GbE | 10 GbE |
| **OS** | Ubuntu 22.04 LTS | Same (or RHEL 9) |
| **Deployment** | Docker Compose | Kubernetes (K3s) for HA |

---

## 17. Vendor-Specific Integration Examples

### 17.1 Siemens S7-1500

```
PLC Model:      S7-1516-3 PN/DP
Firmware:       V3.0+
Protocol:       OPC-UA (built-in server)
Endpoint:       opc.tcp://192.168.30.10:4840
Security:       Basic256Sha256, Sign & Encrypt
Authentication: Username/Password or Certificate
Tag Format:     "DB1".Temperature  →  ns=3;s="DB1"."Temperature"

Steps:
1. Enable OPC-UA server in TIA Portal (PLC Properties → OPC-UA)
2. Configure OPC-UA security (certificate exchange)
3. Export OPC-UA NodeID list from TIA Portal
4. Configure Telegraf inputs.opcua with NodeIDs
```

### 17.2 Allen-Bradley / Rockwell

```
PLC Model:      CompactLogix 5380
Firmware:       V33+
Protocol:       EtherNet/IP (CIP) or OPC-UA (via FactoryTalk Linx Gateway)
Endpoint:       192.168.30.20 (EtherNet/IP)
Tag Format:     "Temperature" (controller-scoped tag name)

Steps:
1. Create controller-scoped tags in Studio 5000
2. Option A: Use Kepware with Allen-Bradley driver → OPC-UA → Telegraf
3. Option B: Use Telegraf inputs.ether_ip plugin (limited support)
4. Option C: Enable OPC-UA on FactoryTalk Linx Gateway
```

### 17.3 Mitsubishi MELSEC

```
PLC Model:      iQ-R R08CPU
Protocol:       MC Protocol (SLMP) over TCP, port 5000
Tag Format:     D0, D1, D2... (Data registers)

Steps:
1. Configure PLC network (built-in Ethernet port)
2. Enable SLMP/MC Protocol communication
3. Use Kepware with Mitsubishi MC Protocol driver
4. Kepware exposes OPC-UA → Telegraf reads OPC-UA
```

### 17.4 Schneider Electric Modicon

```
PLC Model:      Modicon M580
Protocol:       Modbus TCP, port 502
Tag Format:     %MW100 (Memory Word 100) → Modbus register 40101

Steps:
1. Enable Modbus TCP server on M580 (Unity Pro / EcoStruxure)
2. Map PLC variables to Modbus registers
3. Configure Telegraf inputs.modbus with register addresses
4. Apply scale factors as per PLC documentation
```

---

> [!CAUTION]
> **Before connecting to any production PLC**, coordinate with the plant's automation/controls engineer. Incorrect OPC-UA or Modbus access can interfere with PLC scan times and potentially affect production safety systems. Always test on a bench PLC first.

---

> [!TIP]
> **Recommended Implementation Order:**
> 1. Start with one production line (1–3 PLCs)
> 2. Deploy edge gateway + monitoring stack in DMZ
> 3. Validate data accuracy against HMI/SCADA readings for 1–2 weeks
> 4. Roll out to remaining lines
> 5. Enable alerting and notifications
> 6. Scale to multi-plant (if needed)
