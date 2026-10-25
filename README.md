# Vacuula Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://hacs.xyz/docs/faq/custom_repositories)
[![GitHub Release](https://img.shields.io/github/v/release/veronoicc/hass-vacuula?style=for-the-badge)](https://github.com/veronoicc/hass-vacuula/releases)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=for-the-badge)](LICENSE)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=veronoicc&repository=hass-vacuula&category=integration)

Home Assistant integration for [Vacuula](https://github.com/vacuula/vacuula), restoring local control for Neato robot vacuums after the shutdown of the Neato cloud servers.

Supports Gen3 robots (Botvac D3, D4, D5, D6, D7 Connected) and Gen4 robots (Neato D8, D9, D10).

---

## Features

- **Local Control & Real-time Updates**: Real-time push telemetry via Server-Sent Events (SSE) with background reconnect and fallback polling.
- **Modern StateVacuumEntity**: Implements modern Home Assistant vacuum architecture with `VacuumActivity` states (`docked`, `cleaning`, `returning`, `paused`, `error`, `idle`).
- **Native Area & Room Cleaning (`CLEAN_AREA`)**: Native support for room cleaning via persistent map zones using Home Assistant Area cleaning dialogs and `vacuula.clean_zone`.
- **Hub & Child Device Hierarchy**: Automatically registers the Vacuula server as a service hub in Device Registry and attaches all discovered robots as child devices via `via_device`.
- **Comprehensive Sensors**:
  - `sensor.{robot}_battery`: Battery level percentage.
  - `sensor.{robot}_current_action`: Action description (house cleaning, docking, etc.).
  - `sensor.{robot}_error`: Real-time error alerts and UI fault codes.
  - `sensor.vacuula_server_version`: Server firmware/build version.
  - `sensor.vacuula_connected_robots`: Online robot counter.
- **Binary Sensors**:
  - `binary_sensor.{robot}_charging`: Charging contacts status.
  - `binary_sensor.{robot}_dustbin`: Dustbin full or missing notification.
  - `binary_sensor.{robot}_connected`: Robot connectivity to Vacuula server.
  - `binary_sensor.vacuula_server_status`: Server reachable connectivity check.
- **Controls & Switches**:
  - `button.{robot}_locate`: Play identify chime.
  - `button.{robot}_dismiss_alert`: Dismiss active error alert on Gen3 robots.
  - `switch.{robot}_schedule`: Enable or disable onboard schedule.
- **Custom Services**:
  - `vacuula.clean_zone`: Clean a specific room or zone by name.
  - `vacuula.dismiss_alert`: Dismiss active alert.
  - `vacuula.send_raw_command`: Send raw command or ability to the robot.

---

## Installation

### Via HACS (Recommended)

1. Open **HACS** in your Home Assistant instance.
2. Select the three dots in the top right corner and choose **Custom repositories**.
3. Add the repository URL, select category **Integration**, and click **Add**.
4. Search for **Vacuula** and click **Download**.
5. Restart Home Assistant.

### Manual Installation

1. Copy the `custom_components/vacuula` folder to your Home Assistant `<config>/custom_components/` directory.
2. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, navigate to **Settings** > **Devices & Services**.
2. Click **Add Integration** and search for **Vacuula**.
3. Enter your Vacuula server IP or hostname and port (default: 80).
4. Configure optional SSL settings if running behind a reverse proxy.

---

## Services

### `vacuula.clean_zone`

Commands a robot to clean a specific persistent map zone or room.

```yaml
service: vacuula.clean_zone
data:
  serial: "OPS12345-0001"
  zone_name: "Kitchen"
  map_name: "Ground Floor" # Optional
  mode: "turbo"            # "turbo" or "eco"
  navigation_mode: "normal"# "normal", "extra_care", or "deep"
```

### `vacuula.dismiss_alert`

Dismisses the current alert on a Gen3 robot vacuum.

```yaml
service: vacuula.dismiss_alert
data:
  serial: "OPS12345-0001"
```

### `vacuula.send_raw_command`

Sends an arbitrary command or ability.

```yaml
service: vacuula.send_raw_command
data:
  serial: "OPS12345-0001"
  command: "getRobotState"
  params: {}
```
