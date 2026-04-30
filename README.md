# Sigenergy ESS — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration for the **Sigenergy ESS** (inverter + battery + DC EV charger), communicating via Modbus TCP.

## Features

- DC charger monitoring (voltage, current, power, SOC, session energy, state)
- **Car Identifier**: automatically identifies which EV is connected using battery physics
  - LFP vs NMC chemistry fingerprint (instant at connection)
  - Battery capacity estimation (charging and V2H modes)
  - dV/dE method for Zoe V2H stuck-SOC scenarios
  - Nearest-centroid classifier that improves with tagged sessions
- Session logging with 30-second time series
- Persistent notifications when confidence is below 85%

## Supported Cars

Pre-seeded out of the box:

| Car | Chemistry | Capacity |
|-----|-----------|----------|
| Renault Zoe 2022 | NMC | ~52 kWh |
| MG ZS EV 2022 | NMC | ~77 kWh |
| Geely EX5 2026 | LFP | ~60 kWh |

Additional cars can be added via the Options flow.

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS (category: Integration)
2. Search for **Sigenergy ESS** and install
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration** and search for Sigenergy

### Manual

Copy `custom_components/sigen/` to your HA `config/custom_components/` directory and restart.

## Configuration

Enter the Modbus TCP connection details during setup:

| Field | Default | Description |
|-------|---------|-------------|
| Host | — | IP address of the Sigenergy system |
| Port | 502 | Modbus TCP port |
| Slave ID | 1 | Modbus slave/unit ID |
| Scan Interval | 30 s | Poll frequency |
| Read Only | false | Disable all write operations |

## Car Management

Go to **Settings → Devices & Services → Sigenergy ESS → Configure** to:
- View car session counts and prediction accuracy
- Add a new car (name + colour)
- Remove a car

## Services

| Service | Description |
|---------|-------------|
| `sigen.confirm_session_car` | Confirm or correct the identified car for the current/last session |
| `sigen.export_sessions` | Export all session data to `/homeassistant/sigen_sessions_export.json` |

## Sensors Added

| Entity | Description |
|--------|-------------|
| Identified Car | Name of the predicted EV |
| Car ID Confidence | Prediction confidence (%) |
| Session Battery Capacity Estimate | Estimated pack size (kWh) |
| Vehicle Battery Voltage | Pack terminal voltage |
| Charging Current | DC current |
| Output Power | Signed power (negative = V2H) |
| Vehicle SOC | State of charge |
| Session Energy | Energy delivered this session |
| Session Duration | Active session time |
| Charger State | Running state enum |

## License

MIT
