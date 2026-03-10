# ESPHome Sonoff SwitchMan M5 Templates

This repository contains reusable ESPHome packages for Sonoff's SwitchMan M5 wall switches.
It provides separate templates for the **1‑gang** and **2‑gang** models that expose common
substitutions so each device can be configured with a small "mini" file. The only standalone
config kept in-repo is `thp-experiment.yaml`, which is intentionally self-contained for direct
flashing and experimentation.

## Features
- Coupled/decoupled modes with automatic WS2812 LED indicator synchronisation
- Home Assistant configurable LED colors and brightness for on, connecting, and hold states
- SHT4X temperature and humidity sensor support
- Placeholder secrets and linting defaults for safer configuration management
- Local `make lint` checks for YAML linting and ESPHome config validation
- GitHub Actions runs the same lint path on pushes and pull requests

## Behaviour

### Button and relay interaction

- Each channel exposes a virtual channel state (`channel_a_state` / `channel_b_state`) that can be decoupled from its physical relay.
- In **Coupled** mode a button press toggles the relay and keeps the virtual state in sync.
- In **Decoupled** mode a button press only flips the virtual state and fires the Home‑Assistant actions while the relay remains unchanged.

### LED behaviour

- Indicator LEDs mirror the configured channel logic (Coupled vs Decoupled).
- The LED state colors are configurable from Home Assistant for `on`, `connecting`, and `hold`.
- The `Channel ... LED Color Profile` entities are config lights. Their toggle enables or disables that visual profile; it does not report whether the physical LED is currently lit.
- On 2-gang devices, channel A and channel B have separate on/hold color profiles and separate connecting profiles. Channel B's connecting profile is exposed but defaults to disabled, so only channel A shows the Wi-Fi connecting animation until you enable Channel B's connecting profile.
- The default color settings are grouped as per-profile YAML dictionaries in `substitutions`, so each profile can be overridden as one logical block.
- LED profile defaults are automatically seeded into Home Assistant on first boot and again on OTA reflashes. After that, Home Assistant changes persist across normal reboots.

## Usage
Create a per-device YAML that defines the required substitutions and pulls in the
appropriate template via `packages`. Example for the 1‑gang version:

```yaml
substitutions:
  device_friendly_name: "Entrance light switch 1"
  device_name: "entrance-light-switch-1"
  sht4x_present: true
  wifi_ssid: !secret wifi_ssid
  wifi_password: !secret wifi_password
  ota_password: !secret ota_password

packages:
  remote_package:
    url: https://github.com/bitosome/esphome-sonoff
    ref: main
    files:
      - switchman_m5_1_gang.yaml
      - switchman_m5_sht4x.yaml
    refresh: 0s
```

Before building locally, copy `secrets.yaml.example` to `secrets.yaml` and adjust the values.
Set `sht4x_present: false` in a mini config and remove `switchman_m5_sht4x.yaml` from that mini's `packages.remote_package.files` list to exclude the SHT4x package from the compiled firmware.

## Development
Run local lint and config validation before committing:

```bash
cp secrets.yaml.example secrets.yaml
make lint
```

The available targets are:

- `make lint-yaml` to run `yamllint` across all repository YAML files, including `minis/`
- `make lint-esphome` to run `esphome config` against the local standalone templates
- `make lint` to run both checks

## Home Assistant

If you want the logical channel state to appear as a light in Home Assistant while keeping the ESPHome firmware model as a switch, use a Home Assistant template light that wraps the ESPHome switch entity.

An example is provided in [home_assistant_template_lights.example.yaml](/Users/arku02/Repositories/esphome-sonoff/home_assistant_template_lights.example.yaml). Replace `switch.my_switch_channel_a_state` / `switch.my_switch_channel_b_state` with your actual entity IDs.

The `channel_*_on_service`, `channel_*_off_service`, and `channel_*_hold_service` actions require the ESPHome device to be allowed to perform Home Assistant actions in the Home Assistant integration settings. If that permission is disabled, the channel state will still change but the configured Home Assistant action will fail.
