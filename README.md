# TiMotion Desk

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Control and follow a **sit-stand desk with a TiMotion TWD1 Bluetooth module** from Home Assistant: live height, whether it is moving, collision events, named height presets (as many as you like) and move-to-height. Desks that advertise as `stand UP- NNNN` and are driven by the *Stand Up Pls* app use this module, whatever brand is on the frame.

> **Unofficial.** Not affiliated with or endorsed by TiMOTION, any desk brand, Home Assistant, Nabu Casa or the Open Home Foundation. See [NOTICE](NOTICE).

> **Status: early.** Built from a protocol reverse-engineered on one desk (TiMotion TC15S control box, TDH18P handset). The protocol layer and the movement safety logic have unit tests built from real captured frames and the commands were exercised on that desk; the Home Assistant layer is new. See [docs/PROTOCOL.md](docs/PROTOCOL.md) for exactly what is known and how.

## Features

- **Sensors**: *Height* (cm) and *State* (idle, moving up, moving down, reset mode).
- **Binary sensors**: *Moving*, *Collision* (the anti-collision sensor tripped), *Connected* (diagnostic).
- **Select** *Preset*: pick a named height and the desk drives there. It shows the current preset when the desk is within 1 cm of one.
- **Number** *Target height*: type any height from 65 to 130 cm. While moving it shows the target.
- **Buttons**: *Stop*, and a diagnostic *Reset height* (disabled by default).
- Live updates also when the desk is moved with the **handset**.

## Presets

Presets are not limited to the handset's memory buttons and are kept in Home Assistant, not on the desk:

1. *Settings → Devices & services → TiMotion Desk → Configure*.
2. **Add a preset**: a name and a height. Add as many as you need.
3. Edit or remove them from the same menu.

They show up in the *Preset* dropdown immediately. The handset's own memory slots (M1…M3) live in the control box and **cannot be read over Bluetooth**; if you want the same heights, add them as presets by hand.

## Requirements

| | |
|---|---|
| Home Assistant | 2026.10 or newer |
| Bluetooth | A Bluetooth adapter or ESPHome Bluetooth proxy in range of the desk (a connectable one) |
| Desk | A TiMotion **TWD1** module (advertises `stand UP- NNNN`) |

## Installation

1. Open the **Marketplace** (*Settings → Marketplace*, formerly HACS), add `https://github.com/Coollision/ha-timotion-desk` as a custom repository of type **Integration**, download it and restart Home Assistant.
2. The desk is discovered automatically; confirm it under *Settings → Devices & services*. Or add it by hand: *Add integration → TiMotion Desk*.

Close the *Stand Up Pls* phone app first: **the desk accepts only one Bluetooth connection**.

## Keep connected

By default Home Assistant keeps the connection open so height and handset moves show up live. That locks the phone app out. Turn *Keep connected* off in *Configure → Connection* and Home Assistant connects only to send a command and lets go after 30 seconds; the sensors then update only while it is connected.

## Safety

- Movement uses the desk's own move-to-height command, resent every 0.1 s like a held handset button, and always ends with stop frames.
- A move is aborted if the collision sensor trips, the desk moves the wrong way, the desk reports nothing for 3 s, or after 60 s.
- Heights are limited to 65–130 cm and the control box enforces its own limits.
- The *Reset height* button re-measures the desk's lowest point exactly like holding both handset arrows. Leave it disabled unless you need it.
- Keep the desk clear when you move it from automations. The collision sensor is the only obstacle protection.

## Troubleshooting

- **Not discovered / "not in range"**: the desk stops advertising while another client is connected. Close the phone app, wait a few seconds.
- **No height**: the module only starts streaming after its first command; the integration sends a stop frame on connect. If *Connected* is on but there is no height, reload the integration.
- **Height looks offset**: run a reset from the handset (both arrows) so the control box re-measures.

## Development

```bash
python -m unittest discover -s tests -v
```

The codec ([`protocol.py`](custom_components/timotion_desk/protocol.py)) and the movement supervisor ([`motion.py`](custom_components/timotion_desk/motion.py)) have no Home Assistant imports and are covered by the tests. Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/); releases are cut by release-please.

## License

Apache-2.0, see [LICENSE](LICENSE).
