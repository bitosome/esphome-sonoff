# ESPHome Sonoff SwitchMan M5 Templates

This repository contains reusable ESPHome packages for Sonoff's SwitchMan M5 wall switches.
It provides separate templates for the **1‑gang** and **2‑gang** models that expose common
substitutions so each device can be configured with a small "mini" file. The only standalone
config kept in-repo is `thp-experiment.yaml`, which is intentionally self-contained for direct
flashing and experimentation.

## Features
- Coupled/decoupled modes with automatic WS2812 LED indicator synchronisation
- Home Assistant configurable LED colors and brightness for on, connecting, and hold states
- Optional tracked-state LED package for mirroring another Home Assistant entity on a channel LED
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
- The optional tracked-state package adds an extra config light per tracked entity so its brightness and color can be tuned independently.
- When a tracked entity and the local channel are both on, the LED smoothly crossfades between the channel profile and the tracked-state profile.
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
Include `switchman_m5_sht4x.yaml` in a mini's `packages.remote_package.files` list to build in the SHT4x sensor and add ` + SHT4x` to the device model string. Omit that file to exclude the sensor.

To mirror the state of another Home Assistant entity on a channel LED, include `switchman_m5_tracked_state.yaml` as an additional package entry with `path` and `vars`:

```yaml
packages:
  remote_package:
    url: https://github.com/bitosome/esphome-sonoff
    ref: main
    files:
      - switchman_m5_1_gang.yaml
      - path: switchman_m5_tracked_state.yaml
        vars:
          tracked_entity_id: "switch.wc_2_mirror_light_switch_channel_a_state"
          display_channel_id: "a"
    refresh: 0s
```

Add the tracked-state package once per channel LED you want to augment. This allows multiple tracked-state overlays in one device config, for example one package entry for Channel A LED and another for Channel B LED.
The package maps the user-facing channel label internally from `display_channel_id`, so the mini config only needs to specify the local display channel.

To configure multiple tracked entities, repeat the `switchman_m5_tracked_state.yaml` package entry once for each tracked entity you want to display.

Example with multiple tracked entities on one 2-gang switch:

```yaml
packages:
  remote_package:
    url: https://github.com/bitosome/esphome-sonoff
    ref: main
    files:
      - switchman_m5_2_gang.yaml

      - path: switchman_m5_tracked_state.yaml
        vars:
          tracked_entity_id: "switch.wc_2_mirror_light_switch_channel_a_state"
          display_channel_id: "a"

      - path: switchman_m5_tracked_state.yaml
        vars:
          tracked_entity_id: "switch.wc_2_light_switch_1_channel_a_state"
          display_channel_id: "b"
    refresh: 0s
```

In that example:

- Channel A LED displays the state of `switch.wc_2_mirror_light_switch_channel_a_state`.
- Channel B LED displays the state of `switch.wc_2_light_switch_1_channel_a_state`.

Current behavior is one tracked entity per display channel LED. If you include multiple tracked-state entries that all target the same `display_channel_id`, the renderer does not blend them together.

Tracked-state variables:

- `tracked_entity_id`: The Home Assistant entity whose on/off state should be displayed.
- `display_channel_id`: Which local channel LED should display that tracked state. This cannot be derived safely from `tracked_entity_id`, because the tracked entity name does not tell the package whether you want it rendered on Channel A LED or Channel B LED.

The package derives both the user-facing label and the internal ESPHome IDs from the tracked entity object id automatically. For example, `switch.wc_2_mirror_light_switch_channel_a_state` becomes a label like `Wc 2 Mirror Light Switch Channel A State`.

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
