# ESPHome Sonoff SwitchMan M5 Templates

This repository contains reusable ESPHome packages for Sonoff's SwitchMan M5 wall switches.
It provides separate templates for the **1‑gang** and **2‑gang** models that expose common
substitutions so each device can be configured with a small "mini" file.

## Features
- Coupled/decoupled modes with automatic LED indicator synchronisation
- Placeholder secrets and linting defaults for safer configuration management
- GitHub Actions workflow to lint and validate the YAML templates on push

## Behaviour

### Button and relay interaction

- Each channel exposes a virtual button state (`button_a_state` / `button_b_state`) that can be decoupled from its physical relay.
- In **Coupled** mode a button press toggles the relay and keeps the virtual state in sync.
- In **Decoupled** mode a button press only flips the virtual state and fires the Home‑Assistant actions while the relay remains unchanged.

### LED behaviour

- Indicator LEDs mirror the configured channel logic (Coupled vs Decoupled) per template.

## Usage
Create a per-device YAML that defines the required substitutions and pulls in the
appropriate template via `packages`. Example for the 1‑gang version:

```yaml
substitutions:
  device_friendly_name: "Entrance light switch 1"
  device_name: "entrance-light-switch-1"
  wifi_ssid: !secret wifi_ssid
  wifi_password: !secret wifi_password
  ota_password: !secret ota_password

packages:
  remote_package:
    url: https://github.com/bitosome/esphome-sonoff
    ref: main
    files: [switchman_m5_1_gang.yaml]
    refresh: 0s
```

Before building locally, copy `secrets.yaml.example` to `secrets.yaml` and adjust the values.

## Development
Run lint and compile checks before committing:

```bash
yamllint switchman_m5_1_gang.yaml switchman_m5_2_gang.yaml
esphome config switchman_m5_1_gang.yaml
esphome config switchman_m5_2_gang.yaml
```
