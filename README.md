# Hacuula - Home Assistant Vacuula Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://hacs.xyz/docs/faq/custom_repositories)
[![GitHub Release](https://img.shields.io/github/v/release/veronoicc/hass-hacuula?style=for-the-badge)](https://github.com/veronoicc/hass-hacuula/releases)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=for-the-badge)](LICENSE)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=veronoicc&repository=hass-hacuula&category=integration)

> **Important Notice**: This is an independent, community-developed custom integration. It is **not** an official integration by the Vacuula project team and is not maintained, endorsed, or supported by them.
>
> **DO NOT** contact or ask the official Vacuula Discord, GitHub issues, or any other official Vacuula support channels for help regarding this Home Assistant integration—they do not maintain this project. Please submit all questions, bug reports, and feature requests directly to this repository's [Issue Tracker](https://github.com/veronoicc/hass-hacuula/issues).

**Hacuula** connects Home Assistant to your local [Vacuula](https://github.com/vacuula/vacuula) server, restoring complete local control for Neato robot vacuums after the Neato cloud backend shutdown.

Supports Gen3 robots (Botvac D3, D4, D5, D6, D7 Connected) and Gen4 robots (Neato D8, D9, D10).

---

## Features

- **Local Control & Real-time Updates**: Real-time push telemetry via Server-Sent Events (SSE) with background reconnect and fallback polling.
- **Modern StateVacuumEntity**: Implements modern Home Assistant vacuum architecture with `VacuumActivity` states (`docked`, `cleaning`, `returning`, `paused`, `error`, `idle`).
- **Native Area & Room Cleaning (`CLEAN_AREA`)**: Native support for room cleaning via persistent map zones using Home Assistant Area cleaning dialogs and `vacuula.clean_zones`.
- **Live Floor & Run Map Rendering**: Native `image` entities rendering high-DPI auto-cropped floor plans, room zone overlays, No-Go lines, and last cleaning run paths.
- **Select Controls**:
  - `select.{robot}_target_zone`: Choose target room zone (or `all`) for subsequent cleaning runs.
  - `select.{robot}_navigation_mode`: Select navigation mode (normal, extra care, deep, gentle).
  - `select.{robot}_cleaning_mode`: Choose map vs house cleaning on Gen3.
- **Comprehensive Sensors**:
  - `sensor.{robot}_battery`: Battery level percentage.
  - `sensor.{robot}_current_action`: Action description (house cleaning, docking, etc.).
  - `sensor.{robot}_error`: Real-time error alerts and UI fault codes.
  - `sensor.{robot}_last_clean_area`: Last cleaned area in m².
  - `sensor.{robot}_last_clean_duration`: Duration of last cleaning run.
  - `sensor.{robot}_total_cleans`: Lifetime total cleaning runs counter.
  - `sensor.vacuula_server_version`: Server firmware/build version.
  - `sensor.vacuula_connected_robots`: Online robot counter.
- **Binary Sensors**:
  - `binary_sensor.{robot}_charging`: Charging contacts status.
  - `binary_sensor.{robot}_docked`: Dock status indicator.
  - `binary_sensor.{robot}_dustbin`: Dustbin full or missing notification.
  - `binary_sensor.{robot}_connected`: Robot connectivity to Vacuula server.
  - `binary_sensor.vacuula_server_status`: Server reachable connectivity check.
- **Buttons & Controls**:
  - `button.{robot}_locate`: Play identify chime.
  - `button.{robot}_dismiss_alert`: Dismiss active error alert on Gen3 robots.
  - `button.{robot}_refresh_maps`: Reload floor maps, room boundaries, and historical runs.
  - `button.{robot}_explore_map`: Start exploration run to create or update floor map.
  - `button.{robot}_clean_selected_zone`: Clean currently selected target zone.
  - `switch.{robot}_schedule`: Enable or disable onboard schedule.
- **Custom Services**:
  - `vacuula.clean_zones`: Clean one or more room zones or boundary UUIDs.
  - `vacuula.clean_spot`: Localized spot cleaning (Gen3).
  - `vacuula.refresh_maps`: Reload floor maps and run history from the server.
  - `vacuula.dismiss_alert`: Dismiss active alert.
  - `vacuula.send_raw_command`: Send raw command or ability to the robot.

---

## Installation

### Via HACS (Recommended)

1. Open **HACS** in your Home Assistant instance.
2. Select the three dots in the top right corner and choose **Custom repositories**.
3. Enter `https://github.com/veronoicc/hass-hacuula`, select category **Integration**, and click **Add**.
4. Search for **Hacuula** and click **Download**.
5. Restart Home Assistant.

### Manual Installation

1. Copy the `custom_components/vacuula` folder to your Home Assistant `<config>/custom_components/` directory.
2. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, navigate to **Settings** > **Devices & Services**.
2. Click **Add Integration** and search for **Hacuula** (or Vacuula).
3. Enter your Vacuula server IP or hostname and port (default: 80).
4. Configure optional SSL settings if running behind a reverse proxy.

---

## Services

### `vacuula.clean_zones`

Start cleaning one or more room zones on a robot.

```yaml
service: vacuula.clean_zones
target:
  entity_id: vacuum.living_room_vacuum
data:
  zones: "Kitchen, Living Room"
  fan_speed: "turbo"
  navigation_mode: "normal"
```

### `vacuula.clean_spot`

Start localized spot cleaning (Gen3 robots).

```yaml
service: vacuula.clean_spot
target:
  entity_id: vacuum.living_room_vacuum
data:
  width: 200
  height: 200
  fan_speed: "turbo"
```

### `vacuula.refresh_maps`

Reload floor maps and historical runs.

```yaml
service: vacuula.refresh_maps
target:
  entity_id: vacuum.living_room_vacuum
```
