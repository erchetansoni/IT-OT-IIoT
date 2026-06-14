# Multi-Protocol IIoT Data Collection & OT Integration Guide

> **Project**: Avgol IIoT Factory Monitoring System  
> **Scope**: Expanding MVP to support OPC-UA, Modbus, PROFINET & MQTT  
> **Objective**: Zero-downtime integration with existing OT systems  
> **Last Updated**: 2026-06-14  

---

## Table of Contents

- [1. The Universal Data Collection Layer](#1-the-universal-data-collection-layer)
- [2. Current MVP Architecture](#2-current-mvp-architecture)
- [3. Target Multi-Protocol Architecture](#3-target-multi-protocol-architecture)
- [4. Protocol-by-Protocol Integration Strategy](#4-protocol-by-protocol-integration-strategy)
  - [4.1 MQTT (Already Working)](#41-mqtt-already-working)
  - [4.2 OPC-UA Integration](#42-opc-ua-integration)
  - [4.3 Modbus TCP/RTU Integration](#43-modbus-tcprtu-integration)
  - [4.4 PROFINET Integration](#44-profinet-integration)
- [5. Zero-Downtime Integration Principles](#5-zero-downtime-integration-principles)
- [6. Phased Rollout Plan](#6-phased-rollout-plan)
- [7. Network Integration — Tapping Into OT Without Disruption](#7-network-integration--tapping-into-ot-without-disruption)
- [8. Telegraf Unified Configuration](#8-telegraf-unified-configuration)
- [9. Data Normalization — From Multiple Protocols to One Stream](#9-data-normalization--from-multiple-protocols-to-one-stream)
- [10. Risk Assessment & Mitigation](#10-risk-assessment--mitigation)
- [11. Monitoring the Monitoring — Self-Health Checks](#11-monitoring-the-monitoring--self-health-checks)
- [12. Rollback Plan](#12-rollback-plan)

---

## 1. The Universal Data Collection Layer

### The Core Question: Where Does Data Converge?

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │                                                                      │
  │   "Is it the MQTT Broker or Telegraf?"                               │
  │                                                                      │
  │   Answer: ██████████████████████████████████████████████████████     │
  │           ██  TELEGRAF IS THE UNIVERSAL COLLECTION LAYER  ██        │
  │           ██████████████████████████████████████████████████████     │
  │                                                                      │
  └──────────────────────────────────────────────────────────────────────┘
```

### Why Telegraf, Not MQTT Broker?

| Criteria | MQTT Broker (Mosquitto) | Telegraf |
|----------|------------------------|---------|
| **Protocol support** | MQTT only | 300+ input plugins: OPC-UA, Modbus, MQTT, SNMP, HTTP, SQL, S7comm, etc. |
| **Data understanding** | Blind relay — treats payloads as opaque bytes | Parses, transforms, tags, filters, and converts data |
| **Data transformation** | None — what goes in comes out unchanged | JSON → Prometheus, Modbus registers → named metrics, OPC-UA nodes → tagged time-series |
| **Protocol bridging** | Cannot speak OPC-UA or Modbus | Natively reads OPC-UA, Modbus, AND subscribes to MQTT |
| **Output flexibility** | Only MQTT subscribers | Prometheus, InfluxDB, MQTT, Kafka, Files, CloudWatch, etc. |
| **Metric enrichment** | No labels or tags | Adds `host`, `topic`, `line`, `plant` labels automatically |
| **Buffering** | Minimal (QoS-based) | Built-in metric buffer with configurable flush intervals |

### The Relationship

```
  MQTT Broker = A POSTAL SERVICE       (routes letters, doesn't read them)
  Telegraf    = A POLYGLOT TRANSLATOR  (reads every language, writes a universal one)
```

**MQTT Broker** is one of many *transport mechanisms* that Telegraf can consume from. In a multi-protocol world:

```
  OPC-UA Server (PLC)  ─── OPC-UA ───┐
                                      │
  Modbus Device (Sensor) ─ Modbus ───┼──► TELEGRAF ──► Prometheus ──► Grafana
                                      │   (universal    (store)       (visualize)
  MQTT Broker ─────────── MQTT ──────┘    collector)
                                      │
  PROFINET ─(via gateway)─ OPC-UA ───┘
```

> [!IMPORTANT]
> **Key Insight**: In the current MVP, data flows `Simulator → MQTT Broker → Telegraf → Prometheus`. The MQTT Broker acts as a *pass-through* between the simulator and Telegraf. When adding OPC-UA and Modbus protocols, **Telegraf reads those directly** — no MQTT Broker is involved in that path. The MQTT Broker is relevant only for devices that publish via MQTT.

---

## 2. Current MVP Architecture

```
  ┌─────────────────────────────────────────────────────────────┐
  │  CURRENT STATE (Single Protocol: MQTT only)                  │
  │                                                              │
  │  ┌──────────┐   MQTT    ┌──────────┐   MQTT    ┌─────────┐ │
  │  │Simulator │ ────────► │Mosquitto │ ────────► │Telegraf │ │
  │  │(Python)  │  publish  │(Broker)  │ subscribe │(Bridge) │ │
  │  └──────────┘           └──────────┘           └────┬────┘ │
  │                                                     │      │
  │                              HTTP scrape ┌──────────┘      │
  │                                          ▼                 │
  │                                   ┌────────────┐           │
  │                                   │Prometheus  │           │
  │                                   │(TSDB)      │           │
  │                                   └──────┬─────┘           │
  │                                          │ PromQL          │
  │                                          ▼                 │
  │                                   ┌────────────┐           │
  │                                   │Grafana     │           │
  │                                   │(Dashboard) │           │
  │                                   └────────────┘           │
  └─────────────────────────────────────────────────────────────┘
  
  Limitation: Only MQTT protocol. Simulated data, not real PLCs.
```

---

## 3. Target Multi-Protocol Architecture

```
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │  TARGET STATE (Multi-Protocol: OPC-UA + Modbus + PROFINET + MQTT)           │
  │                                                                             │
  │  FACTORY FLOOR (OT Network — Level 0/1/2)                                  │
  │  ═══════════════════════════════════════════                                │
  │                                                                             │
  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌─────────────────┐      │
  │  │ Siemens    │  │ Schneider  │  │ Allen-     │  │ IoT Sensors     │      │
  │  │ S7-1500    │  │ Modicon    │  │ Bradley    │  │ (MQTT-native)   │      │
  │  │            │  │ M580       │  │ CompactLogix│  │                 │      │
  │  │ Protocol:  │  │ Protocol:  │  │ Protocol:  │  │ Protocol:       │      │
  │  │ OPC-UA     │  │ Modbus TCP │  │ EtherNet/IP│  │ MQTT            │      │
  │  │ + PROFINET │  │            │  │ → OPC-UA   │  │                 │      │
  │  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └───────┬─────────┘      │
  │        │               │               │                  │                │
  │  ──────┼───────────────┼───────────────┼──────────────────┼────────────    │
  │        │ OPC-UA        │ Modbus        │ OPC-UA           │ MQTT           │
  │        │ (port 4840)   │ (port 502)    │ (port 4840)      │ (port 8883)    │
  │        │               │               │                  │                │
  │  SERVER ROOM (DMZ — Level 3/3.5)                          │                │
  │  ═══════════════════════════════                           │                │
  │        │               │               │                  │                │
  │        ▼               ▼               ▼                  ▼                │
  │  ┌─────────────────────────────────────────────────────────────────────┐   │
  │  │                                                                     │   │
  │  │                    ██ TELEGRAF (Universal Collector) ██             │   │
  │  │                                                                     │   │
  │  │   ┌─────────────┐ ┌────────────┐ ┌──────────────┐ ┌────────────┐  │   │
  │  │   │inputs.opcua │ │inputs.     │ │inputs.opcua  │ │inputs.     │  │   │
  │  │   │             │ │modbus      │ │(AB via       │ │mqtt_       │  │   │
  │  │   │Reads S7-1500│ │            │ │OPC-UA)       │ │consumer    │  │   │
  │  │   │nodes        │ │Reads       │ │              │ │            │  │   │
  │  │   │directly     │ │registers   │ │Reads tags    │ │Subscribes  │  │   │
  │  │   │             │ │directly    │ │via OPC-UA    │ │to MQTT     │  │   │
  │  │   └─────────────┘ └────────────┘ └──────────────┘ └────────────┘  │   │
  │  │                                                                     │   │
  │  │                    ┌────────────────────────┐                       │   │
  │  │                    │ outputs.prometheus_    │                       │   │
  │  │                    │ client (:9273)         │                       │   │
  │  │                    │                        │                       │   │
  │  │                    │ ALL protocols converge │                       │   │
  │  │                    │ into unified /metrics  │                       │   │
  │  │                    └──────────┬─────────────┘                       │   │
  │  │                               │                                     │   │
  │  └───────────────────────────────┼─────────────────────────────────────┘   │
  │                                  │                                         │
  │                        HTTP scrape (every 5s)                              │
  │                                  │                                         │
  │                                  ▼                                         │
  │                           ┌────────────┐                                   │
  │                           │Prometheus  │                                   │
  │                           │(TSDB)      │                                   │
  │                           └──────┬─────┘                                   │
  │                                  │ PromQL                                  │
  │                                  ▼                                         │
  │                           ┌────────────┐                                   │
  │                           │Grafana     │                                   │
  │                           │(Dashboard) │                                   │
  │                           └────────────┘                                   │
  │                                                                            │
  └────────────────────────────────────────────────────────────────────────────┘
```

> [!TIP]
> Notice that **Telegraf** is the single point where all four protocols converge. No matter if data arrives via OPC-UA, Modbus, or MQTT — it all becomes unified Prometheus metrics exposed on `:9273/metrics`. Downstream components (Prometheus, Grafana) don't need to change at all.

---

## 4. Protocol-by-Protocol Integration Strategy

### 4.1 MQTT (Already Working)

**Status**: ✅ Fully operational in the current MVP

```
  How it works today:
  ──────────────────
  Simulator ──MQTT publish──► Mosquitto ──MQTT subscribe──► Telegraf
  
  In production:
  ──────────────
  IoT Sensors / Smart Devices ──MQTT publish──► Mosquitto ──subscribe──► Telegraf
```

**What's needed for production MQTT**:
- Replace the Python simulator with real MQTT-native IoT devices
- Enable TLS (port 8883) on Mosquitto
- Add username/password or certificate-based authentication
- Telegraf config remains the same — just update broker address and TLS settings

**Telegraf config** (already in place):
```toml
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]        # Change to ssl://mosquitto:8883 for production
  topics = ["factory/plc1"]
  data_format = "json"
```

---

### 4.2 OPC-UA Integration

**Status**: 🔄 To be added

**What is OPC-UA?**
OPC-UA (Open Platform Communications Unified Architecture) is the **industry-standard protocol** for machine-to-machine communication. Most modern PLCs (Siemens S7-1500, Allen-Bradley, ABB, Beckhoff) have built-in OPC-UA servers.

**How data collection works**:
```
  ┌──────────────┐                              ┌──────────────┐
  │              │     OPC-UA (TCP:4840)         │              │
  │  PLC         │ ◄──────────────────────────── │  Telegraf    │
  │  (Siemens    │   READ-ONLY subscription      │  (inputs.    │
  │   S7-1500)   │   to specific nodes           │   opcua)     │
  │              │                               │              │
  │  Built-in    │   Telegraf reads values        │  Converts    │
  │  OPC-UA      │   WITHOUT writing anything    │  to metrics  │
  │  Server      │   to the PLC                  │              │
  │              │                               │              │
  └──────────────┘                              └──────────────┘
```

**Key point — READ ONLY**: Telegraf's OPC-UA input plugin only *reads* data from the PLC. It **never writes** to the PLC. This means:
- ✅ No risk of disrupting PLC logic or process control
- ✅ No risk of overwriting setpoints or control variables
- ✅ Equivalent to a "read-only user" — like someone looking at a gauge without touching it

**Zero-Downtime approach**:

| Step | Action | Risk to OT | Downtime |
|------|--------|------------|----------|
| 1 | Verify PLC has OPC-UA server enabled | None — checking existing config | None |
| 2 | Create a **read-only OPC-UA user** on the PLC | Minimal — adding a user doesn't affect running programs | None |
| 3 | Browse the OPC-UA address space to identify node IDs | None — read-only browse | None |
| 4 | Add `[[inputs.opcua]]` to Telegraf config | None — Telegraf is in the IT/DMZ layer | None |
| 5 | Restart Telegraf container only | None — PLC continues running independently | None (Telegraf only) |
| 6 | Verify metrics in Prometheus | None — passive observation | None |

**Telegraf OPC-UA config to add**:
```toml
[[inputs.opcua]]
  name = "siemens_s7_plc1"
  endpoint = "opc.tcp://192.168.30.100:4840"      # PLC's OPC-UA server
  
  ## Security — use SignAndEncrypt for production
  security_policy = "Basic256Sha256"
  security_mode = "SignAndEncrypt"
  certificate = "/etc/telegraf/certs/client.crt"
  private_key = "/etc/telegraf/certs/client.key"
  
  ## Authentication — read-only user
  auth_method = "UserName"
  username = "telegraf_readonly"
  password = "${OPCUA_PASSWORD}"
  
  ## Subscription-based (server pushes changes — more efficient)
  subscription_interval = "1s"
  
  ## Nodes to monitor (mapped from PLC address space)
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
    name = "motor_rpm"
    namespace = "2"
    identifier_type = "s"
    identifier = "PLC1.MotorRPM"
```

---

### 4.3 Modbus TCP/RTU Integration

**Status**: 🔄 To be added

**What is Modbus?**
Modbus is the **oldest and most widely used** industrial protocol. Found on legacy PLCs, power meters, VFDs (variable frequency drives), and standalone sensors. It uses a simple register-based data model.

**How data collection works**:
```
  ┌──────────────┐                              ┌──────────────┐
  │              │     Modbus TCP (TCP:502)      │              │
  │  Power Meter │ ◄──────────────────────────── │  Telegraf    │
  │  or Legacy   │   READ holding registers     │  (inputs.    │
  │  PLC         │   (Function Code 03/04)       │   modbus)    │
  │              │                               │              │
  │  Modbus      │   Telegraf polls at a         │  Decodes     │
  │  Slave       │   configured interval         │  registers   │
  │  (Server)    │                               │  to metrics  │
  └──────────────┘                              └──────────────┘
```

**Key point — READ ONLY**: Telegraf only uses Modbus **read** function codes (FC03: Read Holding Registers, FC04: Read Input Registers). It **never uses write function codes** (FC05, FC06, FC15, FC16). Zero risk to process control.

**Zero-Downtime approach**:

| Step | Action | Risk to OT | Downtime |
|------|--------|------------|----------|
| 1 | Obtain the device's register map from vendor documentation | None — documentation review | None |
| 2 | Confirm the device's Modbus slave ID and IP address | None — network scan | None |
| 3 | Verify connectivity with a Modbus diagnostic tool (e.g., `mbpoll`) | Minimal — single read request | None |
| 4 | Add `[[inputs.modbus]]` to Telegraf config | None — Telegraf is in the IT/DMZ layer | None |
| 5 | Restart Telegraf container only | None — Modbus device continues operating | None (Telegraf only) |
| 6 | Verify metrics in Prometheus | None — passive observation | None |

> [!WARNING]
> **Modbus polling frequency**: Set the Telegraf interval to be **no faster than the device can handle**. For most PLCs, 1-5 second intervals are safe. Some older devices may struggle with intervals below 500ms. Always check the device manual.

**Telegraf Modbus config to add**:
```toml
[[inputs.modbus]]
  name = "power_meter_line1"
  slave_id = 1
  timeout = "3s"
  controller = "tcp://192.168.30.50:502"         # Modbus device IP
  
  ## Read holding registers (Function Code 03) — READ ONLY
  holding_registers = [
    { name = "temperature",  byte_order = "AB",   data_type = "UINT16",  scale = 0.1,  address = [0] },
    { name = "pressure",     byte_order = "AB",   data_type = "UINT16",  scale = 0.1,  address = [1] },
    { name = "humidity",     byte_order = "AB",   data_type = "UINT16",  scale = 0.1,  address = [2] },
    { name = "motor_rpm",    byte_order = "ABCD", data_type = "UINT32",  scale = 1.0,  address = [3, 4] },
    { name = "vibration",    byte_order = "AB",   data_type = "UINT16",  scale = 0.01, address = [5] },
    { name = "power_kw",     byte_order = "ABCD", data_type = "FLOAT32", scale = 1.0,  address = [6, 7] },
  ]
  
  ## Read discrete inputs (Function Code 02) — READ ONLY
  discrete_inputs = [
    { name = "motor_running",   address = [0] },
    { name = "emergency_stop",  address = [1] },
  ]
```

---

### 4.4 PROFINET Integration

**Status**: 🔄 To be added (indirect — via OPC-UA gateway)

**What is PROFINET?**
PROFINET is Siemens' proprietary **real-time industrial Ethernet** protocol. It operates at **Layer 2** (Data Link Layer) of the OSI model, meaning it does NOT use TCP/IP. This makes it fundamentally different from OPC-UA and Modbus.

**Why PROFINET can't be read directly by Telegraf**:
```
  PROFINET operates at Layer 2 (Ethernet frames)
  Telegraf operates at Layer 4+ (TCP/IP applications)
  
  Layer 2: ███ PROFINET ███   ← Raw Ethernet, no TCP/IP
  Layer 3: ─── IP ──────────
  Layer 4: ─── TCP ─────────
  Layer 7: ─── OPC-UA ─────  ← Where Telegraf lives
           ─── Modbus TCP ──
           ─── MQTT ────────
```

**The Solution: Use the PLC's built-in OPC-UA server as a bridge**

Most PROFINET-capable PLCs (especially Siemens S7-1200/1500) also have a built-in OPC-UA server. The PLC itself already knows all the data from PROFINET devices because it controls them. We simply read that data via OPC-UA.

```
  ┌────────────────────────────────────────────────────────────────┐
  │  PROFINET Network (Layer 2 — Real-time Ethernet)              │
  │                                                                │
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                    │
  │  │PROFINET  │  │PROFINET  │  │PROFINET  │                    │
  │  │IO Device │  │IO Device │  │IO Device │                    │
  │  │(Sensor)  │  │(Drive)   │  │(Valve)   │                    │
  │  └────┬─────┘  └────┬─────┘  └────┬─────┘                    │
  │       │              │             │                           │
  │       └──────────────┴─────────────┘                           │
  │                      │ PROFINET (L2)                           │
  │                      ▼                                         │
  │              ┌──────────────┐                                  │
  │              │  Siemens     │                                  │
  │              │  S7-1500     │                                  │
  │              │  (PROFINET   │                                  │
  │              │   Controller │  ← PLC aggregates all PROFINET  │
  │              │   + OPC-UA   │     device data internally      │
  │              │   Server)    │                                  │
  │              └──────┬───────┘                                  │
  │                     │                                          │
  └─────────────────────┼──────────────────────────────────────────┘
                        │ OPC-UA (TCP:4840)
                        │ READ the same data via OPC-UA nodes
                        ▼
                 ┌──────────────┐
                 │  Telegraf    │  ← Reads PROFINET data indirectly
                 │  (inputs.   │     through the PLC's OPC-UA server
                 │   opcua)    │
                 └──────────────┘
```

**Zero-Downtime approach**:

| Step | Action | Risk to OT | Downtime |
|------|--------|------------|----------|
| 1 | Verify S7-1500 has OPC-UA server enabled (it's built-in) | None | None |
| 2 | In TIA Portal, expose PROFINET IO data as OPC-UA nodes | Minimal — config change, no PLC restart needed on S7-1500 | None |
| 3 | Configure read-only OPC-UA user for Telegraf | None | None |
| 4 | Add `[[inputs.opcua]]` block in Telegraf (same as section 4.2) | None | None |
| 5 | Restart Telegraf container | None — PLC + PROFINET unaffected | None (Telegraf only) |

> [!NOTE]
> **PROFINET data is always collected through a gateway protocol (OPC-UA)**. You do not need a separate PROFINET driver or adapter. The PLC that controls the PROFINET network already has all the data, and you read it via its OPC-UA server. This is the industry-standard approach.

---

## 5. Zero-Downtime Integration Principles

### The Golden Rules

```
  ╔══════════════════════════════════════════════════════════════════════╗
  ║                                                                      ║
  ║   RULE 1: NEVER TOUCH THE CONTROL PLANE                             ║
  ║   ─────────────────────────────────────                              ║
  ║   We only READ data. We never write to PLCs, modify control         ║
  ║   logic, change setpoints, or interfere with SCADA systems.         ║
  ║                                                                      ║
  ║   RULE 2: ADD, NEVER MODIFY                                         ║
  ║   ──────────────────────────                                         ║
  ║   We ADD monitoring infrastructure alongside existing systems.       ║
  ║   We never modify existing network topology or remove existing       ║
  ║   connections.                                                       ║
  ║                                                                      ║
  ║   RULE 3: MONITOR FROM A SEPARATE NETWORK SEGMENT                   ║
  ║   ─────────────────────────────────────────────────                   ║
  ║   All IIoT monitoring infrastructure (Telegraf, Prometheus,         ║
  ║   Grafana) lives in the DMZ/IT network. Factory floor (OT)          ║
  ║   remains untouched.                                                 ║
  ║                                                                      ║
  ║   RULE 4: FAIL SILENTLY                                             ║
  ║   ─────────────────────                                              ║
  ║   If our monitoring system fails, the factory keeps running.        ║
  ║   The PLCs don't depend on our system. We are passive observers.    ║
  ║                                                                      ║
  ║   RULE 5: ONE PROTOCOL AT A TIME                                    ║
  ║   ─────────────────────────────                                      ║
  ║   Integrate each protocol sequentially, validate thoroughly,        ║
  ║   before moving to the next. Never do a "big bang" deployment.      ║
  ║                                                                      ║
  ╚══════════════════════════════════════════════════════════════════════╝
```

### What Makes This Integration Zero-Downtime?

```
  EXISTING OT SYSTEM (unchanged)              NEW IIoT MONITORING (added alongside)
  ══════════════════════════════              ══════════════════════════════════════
  
  ┌────────┐    PROFINET     ┌────────┐
  │Sensor  │ ──────────────► │  PLC   │      ← This path is UNTOUCHED
  └────────┘                 │        │
                             │        │ ◄── Existing SCADA/HMI reads here
                             │        │     (this connection is UNTOUCHED)
                             │        │
                             │  OPC-UA│ ◄── NEW: Telegraf reads here
                             │ Server │     (additional OPC-UA client)
                             └────────┘
                                  │
                                  │  NEW connection (read-only)
                                  │  Does NOT affect existing connections
                                  ▼
                            ┌──────────┐
                            │ Telegraf │  ← NEW container in DMZ
                            └──────────┘
```

**Analogy**: Imagine a factory floor with existing CCTV cameras. We are adding *new* CCTV cameras alongside the existing ones. We don't unplug the existing cameras. We don't move the existing monitors. We just add new cameras and new monitors in a separate room.

---

## 6. Phased Rollout Plan

### Phase 0: Preparation (Week 1) — No Changes to OT

| # | Task | Who | Impact on OT |
|---|------|-----|-------------|
| 1 | Inventory all PLCs, sensors, and their protocols | OT Engineer + IT | **None** — documentation only |
| 2 | Document IP addresses, Modbus slave IDs, OPC-UA endpoints | OT Engineer | **None** — reading existing config |
| 3 | Collect register maps / OPC-UA node lists from vendor manuals | OT Engineer | **None** — paperwork |
| 4 | Design the network connectivity plan (VLANs, firewall rules) | Network Engineer | **None** — planning only |
| 5 | Set up a test bench with OPC-UA simulator + Modbus simulator | IT Developer | **None** — isolated test environment |

### Phase 1: Validate with Simulators (Week 2) — No Changes to OT

```
  ┌──────────────────────────────────────────────────────────────┐
  │  TEST ENVIRONMENT (completely isolated from production OT)    │
  │                                                              │
  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
  │  │ OPC-UA       │  │ Modbus       │  │ MQTT         │      │
  │  │ Simulator    │  │ Simulator    │  │ Simulator    │      │
  │  │ (open62541)  │  │ (diagslave)  │  │ (existing)   │      │
  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
  │         │                 │                  │               │
  │         └─────────────────┼──────────────────┘               │
  │                           ▼                                  │
  │                    ┌──────────────┐                          │
  │                    │  Telegraf    │  Test multi-protocol     │
  │                    │  (dev)       │  config here first       │
  │                    └──────┬───────┘                          │
  │                           ▼                                  │
  │                    ┌──────────────┐                          │
  │                    │ Prometheus   │                          │
  │                    └──────┬───────┘                          │
  │                           ▼                                  │
  │                    ┌──────────────┐                          │
  │                    │ Grafana      │  Verify dashboards       │
  │                    └──────────────┘                          │
  └──────────────────────────────────────────────────────────────┘
```

| # | Task | Who | Impact on OT |
|---|------|-----|-------------|
| 1 | Deploy OPC-UA simulator (e.g., `open62541` or `Prosys OPC-UA Simulation Server`) | IT Developer | **None** — separate test environment |
| 2 | Deploy Modbus simulator (e.g., `diagslave` or `ModRSsim2`) | IT Developer | **None** — separate test environment |
| 3 | Configure Telegraf with all three input plugins (OPC-UA + Modbus + MQTT) | IT Developer | **None** — separate test environment |
| 4 | Verify metrics appear in Prometheus with correct names, tags, units | IT Developer | **None** |
| 5 | Build multi-protocol Grafana dashboard | IT Developer | **None** |
| 6 | Load test — verify Telegraf handles the expected data volume | IT Developer | **None** |

### Phase 2: First Real OPC-UA Connection (Week 3) — Minimal OT Touch

| # | Task | Who | Impact on OT |
|---|------|-----|-------------|
| 1 | Verify target PLC has OPC-UA server enabled | OT Engineer | **None** — checking existing state |
| 2 | Create a **read-only** OPC-UA user account on the PLC | OT Engineer | **Minimal** — user creation, no PLC restart |
| 3 | Open firewall rule: Telegraf server → PLC port 4840 (TCP, one-way) | Network Engineer | **None** — additive firewall rule |
| 4 | Add `[[inputs.opcua]]` block to Telegraf config | IT Developer | **None** — Telegraf is in DMZ |
| 5 | Restart Telegraf container | IT Developer | **None** — PLC unaffected |
| 6 | Monitor for 24-48 hours — verify no impact on PLC scan cycle times | OT Engineer | **Observation only** |
| 7 | Compare OPC-UA data in Grafana against HMI/SCADA readings for accuracy | OT + IT | **None** — cross-referencing |

> [!CAUTION]
> **During Phase 2, monitor the PLC's CPU load and scan cycle time.** OPC-UA server operations consume some PLC CPU. For Siemens S7-1500, the OPC-UA server has a configurable "maximum number of sessions" and "server update rate" that can be tuned to limit resource usage. Typical impact is <2% CPU for a single monitoring client.

### Phase 3: Add Modbus Devices (Week 4)

| # | Task | Who | Impact on OT |
|---|------|-----|-------------|
| 1 | Identify Modbus devices to connect (power meters, sensors) | OT Engineer | **None** |
| 2 | Open firewall rule: Telegraf server → Modbus device port 502 | Network Engineer | **None** — additive rule |
| 3 | Add `[[inputs.modbus]]` block to Telegraf config | IT Developer | **None** |
| 4 | Restart Telegraf container | IT Developer | **None** — Modbus devices unaffected |
| 5 | Verify register values match device displays | OT Engineer | **None** — cross-referencing |
| 6 | Monitor for 24-48 hours | OT + IT | **Observation only** |

### Phase 4: PROFINET via OPC-UA (Week 5)

| # | Task | Who | Impact on OT |
|---|------|-----|-------------|
| 1 | In TIA Portal, expose PROFINET IO device data as OPC-UA nodes | OT Engineer | **Minimal** — config change in engineering tool |
| 2 | Download updated PLC config (if needed — many S7-1500 allow online changes) | OT Engineer | **Minimal** — online change possible |
| 3 | Add new OPC-UA nodes to existing `[[inputs.opcua]]` block | IT Developer | **None** |
| 4 | Restart Telegraf | IT Developer | **None** |
| 5 | Validate PROFINET device data in Grafana | OT + IT | **None** |

### Phase 5: Production Hardening (Week 6-7)

| # | Task | Who | Impact on OT |
|---|------|-----|-------------|
| 1 | Enable TLS on all connections (MQTT, OPC-UA) | IT Developer + OT | **None** — security upgrade |
| 2 | Add Grafana alerting rules | IT Developer | **None** |
| 3 | Add Prometheus persistent storage | IT Developer | **None** |
| 4 | Document all configurations and runbooks | IT Developer | **None** |
| 5 | Hand over dashboards to operations team | Everyone | **None** |

---

## 7. Network Integration — Tapping Into OT Without Disruption

### Current Network (Before Integration)

```
  ┌──────────────────────────────────────────────────────────┐
  │  OT NETWORK (Existing — completely isolated)             │
  │                                                          │
  │  VLAN 30: Control Network (192.168.30.0/24)              │
  │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐               │
  │  │PLC 1 │  │PLC 2 │  │VFD 1 │  │Meter │               │
  │  │.100  │  │.101  │  │.50   │  │.51   │               │
  │  └──────┘  └──────┘  └──────┘  └──────┘               │
  │       │        │         │         │                    │
  │       └────────┴─────────┴─────────┘                    │
  │                    │                                     │
  │  VLAN 20: SCADA Network (192.168.20.0/24)               │
  │  ┌──────────┐  ┌───────┐                                │
  │  │ SCADA    │  │ HMI   │                                │
  │  │ Server   │  │ Panel │                                │
  │  └──────────┘  └───────┘                                │
  │                                                          │
  │  ◄── NO connection to IT network ──►                    │
  │                                                          │
  └──────────────────────────────────────────────────────────┘
```

### After Integration (OT network unchanged, new DMZ added)

```
  ┌──────────────────────────────────────────────────────────┐
  │  OT NETWORK (UNCHANGED — nothing removed or moved)       │
  │                                                          │
  │  VLAN 30: Control Network (192.168.30.0/24)              │
  │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐               │
  │  │PLC 1 │  │PLC 2 │  │VFD 1 │  │Meter │               │
  │  │.100  │  │.101  │  │.50   │  │.51   │               │
  │  └──┬───┘  └──┬───┘  └──┬───┘  └──┬───┘               │
  │     │         │         │         │                     │
  │     └─────────┴─────────┴─────────┘                     │
  │                    │                                     │
  │  VLAN 20: SCADA Network (192.168.20.0/24)               │
  │  ┌──────────┐  ┌───────┐                                │
  │  │ SCADA    │  │ HMI   │  ← STILL WORKS, UNCHANGED     │
  │  │ Server   │  │ Panel │                                │
  │  └──────────┘  └───────┘                                │
  │                                                          │
  └──────────────────┬───────────────────────────────────────┘
                     │
              ┌──────┴──────┐
              │  FIREWALL   │  ← NEW: Controlled access
              │  (Layer 3)  │     Only specific ports allowed
              │             │     OPC-UA (4840), Modbus (502)
              │  Rules:     │     Direction: DMZ → OT only
              │  ALLOW:     │     No OT → DMZ traffic
              │  4840/tcp   │
              │  502/tcp    │
              │  DENY: *    │
              └──────┬──────┘
                     │
  ┌──────────────────┴───────────────────────────────────────┐
  │  NEW: IIoT DMZ (172.20.0.0/24)                          │
  │                                                          │
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
  │  │Telegraf  │  │Mosquitto │  │Prometheus│              │
  │  │(Collect) │  │(MQTT)    │  │(Store)   │              │
  │  └──────────┘  └──────────┘  └──────────┘              │
  │                                                          │
  │  ┌──────────┐                                           │
  │  │Grafana   │                                           │
  │  │(Visualize│                                           │
  │  └──────────┘                                           │
  │                                                          │
  └──────────────────────────────────────────────────────────┘
```

### Firewall Rules — Minimum Required Openings

| # | Source | Destination | Port | Protocol | Direction | Purpose |
|---|--------|-------------|------|----------|-----------|---------|
| 1 | Telegraf (172.20.0.x) | PLC OPC-UA (192.168.30.100) | 4840 | TCP | DMZ → OT | OPC-UA read |
| 2 | Telegraf (172.20.0.x) | Modbus Device (192.168.30.50) | 502 | TCP | DMZ → OT | Modbus read |
| 3 | **DENY ALL** | OT Network | * | * | OT → DMZ | **Block reverse traffic** |

> [!IMPORTANT]
> **The firewall rules are unidirectional.** Telegraf initiates connections TO the OT network. The OT network NEVER initiates connections to the DMZ. If Telegraf goes down, the OT network doesn't even notice — it's as if someone stopped looking at a gauge.

---

## 8. Telegraf Unified Configuration

This is the **complete Telegraf configuration** that supports all four protocols simultaneously:

```toml
# ═══════════════════════════════════════════════════════════════════════
# TELEGRAF — UNIVERSAL DATA COLLECTION LAYER
# Supports: OPC-UA, Modbus TCP, PROFINET (via OPC-UA), MQTT
# ═══════════════════════════════════════════════════════════════════════

[agent]
  interval = "5s"
  flush_interval = "5s"
  hostname = "iiot-collector-01"
  
  ## Buffer settings for reliability
  metric_buffer_limit = 10000
  metric_batch_size = 1000

# ─────────────────────────────────────────────────────────────────────
# INPUT 1: OPC-UA — Siemens S7-1500 (includes PROFINET IO data)
# ─────────────────────────────────────────────────────────────────────
[[inputs.opcua]]
  name = "plc1_siemens"
  endpoint = "opc.tcp://192.168.30.100:4840"
  
  security_policy = "Basic256Sha256"
  security_mode = "SignAndEncrypt"
  certificate = "/etc/telegraf/certs/opcua-client.crt"
  private_key = "/etc/telegraf/certs/opcua-client.key"
  
  auth_method = "UserName"
  username = "telegraf_readonly"
  password = "${OPCUA_PASSWORD}"
  
  subscription_interval = "1s"
  connect_timeout = "10s"
  request_timeout = "5s"
  
  ## Tags to identify this data source
  [inputs.opcua.tags]
    protocol = "opcua"
    line = "line1"
    plant = "avgol-india"
  
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
    name = "motor_rpm"
    namespace = "2"
    identifier_type = "s"
    identifier = "PLC1.MotorRPM"

  [[inputs.opcua.nodes]]
    name = "vibration"
    namespace = "2"
    identifier_type = "s"
    identifier = "PLC1.Vibration"

# ─────────────────────────────────────────────────────────────────────
# INPUT 2: Modbus TCP — Power Meter / Legacy Sensors
# ─────────────────────────────────────────────────────────────────────
[[inputs.modbus]]
  name = "power_meter_line1"
  slave_id = 1
  timeout = "3s"
  controller = "tcp://192.168.30.50:502"
  
  ## Tags to identify this data source
  [inputs.modbus.tags]
    protocol = "modbus"
    line = "line1"
    plant = "avgol-india"
  
  ## Holding registers (Function Code 03 — READ ONLY)
  holding_registers = [
    { name = "power_kw",     byte_order = "ABCD", data_type = "FLOAT32", scale = 1.0,  address = [0, 1] },
    { name = "voltage",      byte_order = "ABCD", data_type = "FLOAT32", scale = 1.0,  address = [2, 3] },
    { name = "current",      byte_order = "ABCD", data_type = "FLOAT32", scale = 1.0,  address = [4, 5] },
    { name = "power_factor", byte_order = "AB",   data_type = "UINT16",  scale = 0.01, address = [6] },
  ]

# ─────────────────────────────────────────────────────────────────────
# INPUT 3: MQTT — IoT Sensors & Existing Simulator
# ─────────────────────────────────────────────────────────────────────
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]
  
  ## Subscribe to all factory topics
  topics = [
    "factory/plc1",
    "factory/+/sensors",
    "factory/+/status"
  ]
  
  data_format = "json"
  
  ## Tags to identify this data source
  [inputs.mqtt_consumer.tags]
    protocol = "mqtt"

# ─────────────────────────────────────────────────────────────────────
# OUTPUT: Prometheus Metrics Endpoint (unified for all inputs)
# ─────────────────────────────────────────────────────────────────────
[[outputs.prometheus_client]]
  listen = ":9273"
  
  ## Expiry — remove stale metrics after 60s of no updates
  expiration_interval = "60s"
```

### What This Produces

All protocols converge into a single `/metrics` endpoint:

```
# FROM OPC-UA (Siemens PLC)
opcua_temperature{host="iiot-collector-01",protocol="opcua",line="line1",plant="avgol-india"} 78.5
opcua_pressure{host="iiot-collector-01",protocol="opcua",line="line1",plant="avgol-india"} 25.3
opcua_motor_rpm{host="iiot-collector-01",protocol="opcua",line="line1",plant="avgol-india"} 2100

# FROM MODBUS (Power Meter)
modbus_power_kw{host="iiot-collector-01",protocol="modbus",line="line1",plant="avgol-india"} 98.76
modbus_voltage{host="iiot-collector-01",protocol="modbus",line="line1",plant="avgol-india"} 415.2
modbus_current{host="iiot-collector-01",protocol="modbus",line="line1",plant="avgol-india"} 142.5

# FROM MQTT (IoT Sensors / Simulator)
mqtt_consumer_temperature{host="iiot-collector-01",protocol="mqtt",topic="factory/plc1"} 78
mqtt_consumer_pressure{host="iiot-collector-01",protocol="mqtt",topic="factory/plc1"} 25
```

> [!TIP]
> Notice the **`protocol` tag** on every metric. This allows you to filter in Grafana by protocol: `{protocol="opcua"}` for OPC-UA data, `{protocol="modbus"}` for Modbus data, etc. The downstream pipeline (Prometheus + Grafana) doesn't care which protocol the data came from — it's all the same format.

---

## 9. Data Normalization — From Multiple Protocols to One Stream

### The Transformation Diagram

```
  RAW DATA (Different formats)              NORMALIZED (Unified format)
  ══════════════════════════                ═══════════════════════════
  
  OPC-UA Node:                              
  {                                         ┌──────────────────────────────┐
    "NodeId": "ns=2;s=PLC1.Temp",          │ opcua_temperature            │
    "Value": {"Body": 78.5},        ─────► │   {protocol="opcua",         │
    "StatusCode": "Good",                   │    line="line1"}             │
    "Timestamp": "2026-..."                │   VALUE: 78.5                │
  }                                         └──────────────────────────────┘
  
  Modbus Register:                          
  Register 40001 = 0x030D             ─────► ┌──────────────────────────────┐
  (raw uint16, scale ÷10)                   │ modbus_temperature           │
                                            │   {protocol="modbus",        │
                                            │    line="line1"}             │
                                            │   VALUE: 78.1                │
                                            └──────────────────────────────┘
  
  MQTT JSON:                                
  {                                         ┌──────────────────────────────┐
    "temperature": 78,               ─────► │ mqtt_consumer_temperature    │
    "pressure": 25                          │   {protocol="mqtt",          │
  }                                         │    topic="factory/plc1"}     │
                                            │   VALUE: 78                  │
                                            └──────────────────────────────┘
  
  
  ALL THREE ──► Prometheus (same TSDB) ──► Grafana (same dashboard)
```

### Metric Naming Convention

| Source Protocol | Telegraf Input Plugin | Metric Name Pattern | Example |
|----------------|----------------------|--------------------:|---------|
| OPC-UA | `inputs.opcua` | `opcua_{node_name}` | `opcua_temperature` |
| Modbus | `inputs.modbus` | `modbus_{register_name}` | `modbus_power_kw` |
| MQTT | `inputs.mqtt_consumer` | `mqtt_consumer_{json_field}` | `mqtt_consumer_temperature` |
| PROFINET | `inputs.opcua` (via PLC) | `opcua_{node_name}` | `opcua_vibration` |

### Grafana PromQL — Querying Across Protocols

```promql
# Temperature from ALL protocols combined
{__name__=~"(opcua|modbus|mqtt_consumer)_temperature"}

# Filter by protocol
opcua_temperature{line="line1"}

# Filter by production line
{line="line1", protocol="opcua"}

# Aggregate across all sources
avg({__name__=~".*_temperature"})
```

---

## 10. Risk Assessment & Mitigation

### Risk Matrix

| # | Risk | Probability | Impact | Mitigation |
|---|------|------------|--------|------------|
| 1 | **OPC-UA read increases PLC CPU load** | Low | Medium | Limit Telegraf to 1-second minimum subscription interval. Monitor PLC diagnostics for first 48 hours. S7-1500 OPC-UA server is designed for this. |
| 2 | **Modbus polling conflicts with existing SCADA** | Low | Medium | Ensure Telegraf doesn't exceed device's max connection limit. Coordinate with SCADA team on polling schedule. |
| 3 | **Network firewall misconfiguration** | Medium | High | Test all firewall rules in lab first. Use specific IP-to-IP rules, not VLAN-wide. Have rollback rules ready. |
| 4 | **Telegraf consumes too much OT network bandwidth** | Very Low | Medium | Each OPC-UA subscription for 10 nodes = ~2 KB/s. Negligible on 100Mbps+ industrial Ethernet. |
| 5 | **Incorrect Modbus register mapping** | Medium | None (to OT) | Only affects data quality in dashboards. Use `mbpoll` tool to verify registers before Telegraf config. No impact on devices. |
| 6 | **PLC OPC-UA server not enabled** | Medium | None | Requires OT engineer to enable in PLC programming tool (e.g., TIA Portal). No impact on running PLC program. |
| 7 | **Certificate management for OPC-UA TLS** | Medium | Low | Use self-signed certs for initial testing. Plan PKI infrastructure for production. |

### Impact on Existing Systems — What Changes and What Doesn't

| Component | Changes? | Details |
|-----------|----------|---------|
| PLC programs (ladder logic / structured text) | ❌ No | We never modify PLC programs |
| PLC scan cycle | ❌ No* | *OPC-UA server runs in a separate task with lower priority than the main scan cycle |
| SCADA system | ❌ No | We don't touch SCADA. Both SCADA and Telegraf read from the PLC independently |
| HMI panels | ❌ No | HMIs continue to read from PLCs as before |
| Existing network switches | ❌ No | We add a new connection, not modify existing ones |
| Existing network cabling | ❌ No | We use available Ethernet ports on PLCs |
| OT Firewall | ✅ Yes | Additive rules only — open specific ports from DMZ to OT |
| DMZ Network | ✅ Yes | New VLAN/subnet for IIoT monitoring infrastructure |
| PLC user accounts | ✅ Yes | New read-only OPC-UA user created on PLC |
| PLC OPC-UA server config | ✅ Yes (if not already enabled) | Enable OPC-UA server feature (no PLC program restart needed on S7-1500) |

---

## 11. Monitoring the Monitoring — Self-Health Checks

### Telegraf Internal Metrics

Telegraf exposes its own health metrics that we should monitor:

```promql
# Is Telegraf collecting data from all plugins?
internal_gather_errors_total{input="opcua"}    # Should be 0
internal_gather_errors_total{input="modbus"}   # Should be 0
internal_gather_errors_total{input="mqtt_consumer"}  # Should be 0

# Collection latency per plugin
internal_gather_elapsed_ns{input="opcua"}      # Should be < 1000ms
internal_gather_elapsed_ns{input="modbus"}     # Should be < 500ms

# Metrics gathered per plugin
internal_metrics_gathered{input="opcua"}       # Should be > 0
internal_metrics_gathered{input="modbus"}      # Should be > 0
```

### Grafana Alert Rules to Create

| Alert | Condition | Severity | Notification |
|-------|-----------|----------|-------------|
| OPC-UA Connection Lost | `internal_gather_errors_total{input="opcua"}` increases for >2 min | Warning | Slack / Email |
| Modbus Connection Lost | `internal_gather_errors_total{input="modbus"}` increases for >2 min | Warning | Slack / Email |
| MQTT Broker Unreachable | `internal_gather_errors_total{input="mqtt_consumer"}` increases for >2 min | Warning | Slack / Email |
| No Data From Any Source | All `*_temperature` metrics are absent for >5 min | Critical | PagerDuty / SMS |
| Telegraf Container Down | Prometheus target `telegraf:9273` is DOWN | Critical | PagerDuty / SMS |

---

## 12. Rollback Plan

### If Issues Arise During Integration

```
  SITUATION                          ACTION                           TIME
  ═══════════                        ══════                           ════

  OPC-UA causing PLC issues?    →   Remove [[inputs.opcua]] block    2 min
                                     from telegraf.conf and restart
                                     Telegraf container.
                                     PLC instantly unaffected.

  Modbus causing device issues? →   Remove [[inputs.modbus]] block   2 min
                                     and restart Telegraf container.
                                     Device instantly unaffected.

  Network issues?               →   Close firewall rules             1 min
                                     (ports 4840, 502) on the
                                     OT-DMZ firewall.
                                     Complete isolation restored.

  Everything broken?            →   docker compose down              10 sec
                                     The ENTIRE IIoT monitoring
                                     stack shuts down.
                                     OT network doesn't notice.
                                     Factory keeps running.
```

> [!CAUTION]
> **The ultimate safety net**: If anything goes wrong, `docker compose down` shuts down the entire IIoT monitoring stack instantly. The factory floor is **completely independent** of our monitoring system. The PLCs, SCADA, HMIs — they all continue running as if our system never existed. This is by design.

---

## Summary — The Big Picture

```
  ┌────────────────────────────────────────────────────────────────────┐
  │                                                                    │
  │   BEFORE (Current MVP)          AFTER (Multi-Protocol)            │
  │   ════════════════════          ══════════════════════             │
  │                                                                    │
  │   Protocols: MQTT only          Protocols: OPC-UA, Modbus,        │
  │                                             PROFINET, MQTT        │
  │                                                                    │
  │   Data Source: Simulator         Data Source: Real PLCs +          │
  │                                              Sensors + IoT        │
  │                                                                    │
  │   Collection: Telegraf           Collection: TELEGRAF              │
  │   (MQTT consumer only)          (OPC-UA + Modbus + MQTT inputs)   │
  │                                                                    │
  │   Changed:                       Unchanged:                        │
  │   • Telegraf config              • Prometheus (same scrape)        │
  │     (add input blocks)           • Grafana (same data source)      │
  │   • Firewall rules               • MQTT Broker (if still needed)  │
  │     (additive only)              • All OT systems                  │
  │   • PLC user accounts            • Docker Compose structure        │
  │     (read-only)                  • Data pipeline pattern           │
  │                                                                    │
  │   Risk to factory: ZERO          Downtime: ZERO                   │
  │                                                                    │
  └────────────────────────────────────────────────────────────────────┘
```

> [!TIP]
> **The key takeaway**: Telegraf is the universal collection layer. It speaks every industrial protocol natively. We only modify Telegraf's configuration file to add new protocol inputs. Everything downstream (Prometheus, Grafana) stays exactly the same. And everything upstream (PLCs, SCADA, factory floor) remains completely untouched and unaware of our monitoring system.
