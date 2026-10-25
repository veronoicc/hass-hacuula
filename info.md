# Hacuula for Home Assistant

Independent community integration for Neato Botvac and D-series robot vacuums connecting to a local [Vacuula](https://github.com/vacuula/vacuula) server.

> **Note**: This is an independent community project and is not an official integration by the Vacuula team. **DO NOT** contact or ask the official Vacuula Discord or other Vacuula support channels for help with this integration, as they do not maintain it. Please use this repository's issue tracker for all support.

## Features

- Local control without cloud dependencies
- Real-time updates via Server-Sent Events (SSE)
- Room and zone cleaning support (`VacuumEntityFeature.CLEAN_AREA`)
- Floor map and last run map image rendering
- Navigation mode and target zone selectors
- Battery, clean duration, area, and diagnostic sensors
- Identify locate button and schedule switch controls

## Setup

1. Restart Home Assistant after downloading.
2. Go to **Settings** > **Devices & Services** > **Add Integration**.
3. Search for **Hacuula**.
4. Enter your Vacuula server host and port.
