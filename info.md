# Vacuula Integration for Home Assistant

Local control integration for Neato Botvac and D-series robot vacuums powered by [Vacuula](https://github.com/vacuula/vacuula).

## Features

- Local control without cloud dependencies
- Real-time updates via Server-Sent Events (SSE)
- Room and zone cleaning support (`VacuumEntityFeature.CLEAN_AREA`)
- Full battery, action, and diagnostic sensors
- Start, pause, stop, return to base, and spot clean commands
- Identify locate button and schedule switch controls

## Setup

1. Restart Home Assistant after downloading.
2. Go to **Settings** > **Devices & Services** > **Add Integration**.
3. Search for **Vacuula**.
4. Enter your Vacuula server host and port.
