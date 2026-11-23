# Archive: designs not used in the final setup

The van uses **VanTurtle Smart Controllers over WiFi** (see the main `README.md`). Before that
was settled, four other ways to connect the fans were worked out. Their documents and firmware
are kept here for reference only; nothing in this folder is needed for the final setup.

| Path | What |
|---|---|
| `hardware/option-e-vanturtle-esp32.md` | E: VanTurtle DIY board + an ESP32 at each fan, over WiFi |
| `hardware/option-v-vanturtle.md` | V: VanTurtle DIY board on the Pi's own I2C pins, cables to the roof |
| `hardware/option-a-tap.md` | A: ESP32 at each fan sending infrared-remote packets on the receiver line |
| `hardware/option-c-replacement.md` | C: ESP32 board replacing the fan's own controller |
| `firmware/` | ESPHome firmware for A, C (`common.yaml`, `option-a*.yaml`, `option-c.yaml`) and E (`vanturtle-board.yaml`) |
| `docs/mqtt-contract.md` | MQTT topics between the driver and the A, C and E firmware |
| `tests/test_packet.cpp`, `tests/test_relay.cpp` | Desktop tests of the A packet encoder and the E relay |
| `install.sh` | The installer used before the SetupHelper package; it also enabled I2C for option V |

Paths inside these documents were written before the move: `firmware/` now means
`archive/firmware/`, `docs/mqtt-contract.md` means `archive/docs/mqtt-contract.md`, and
`option-w-vanturtle-wifi.md` is now `hardware/vanturtle-smart-controller.md`.

**The driver can still run all of them.** `dbus-maxxfan-bridge` keeps the backends
`vanturtle-esp32` (E), `vanturtle` (V) and `mqtt` (A, C), chosen per fan in `config.ini`, and
`tests/` still tests them (`test_vanturtle.py`, `test_vtboard.py`, parts of `test_driver.py`).

```sh
# from the project folder
mkdir -p .build && c++ -std=c++17 -o .build/test_relay archive/tests/test_relay.cpp && .build/test_relay
mkdir -p .build && c++ -std=c++17 -o .build/test_packet archive/tests/test_packet.cpp && .build/test_packet
cd archive/firmware && ../../.build/venv/bin/esphome compile vanturtle-board.yaml   # needs secrets.yaml
```

## The options compared

| | **W — VanTurtle Smart Controller, WiFi** | **E — VanTurtle DIY board + ESP32 at each fan** | **V — VanTurtle board on the Pi** | **A — Tap board** | **C — Replacement controller** |
|---|---|---|---|---|---|
| Document | `hardware/vanturtle-smart-controller.md` (in use) | `archive/hardware/option-e-vanturtle-esp32.md` | `archive/hardware/option-v-vanturtle.md` | `archive/hardware/option-a-tap.md` | `archive/hardware/option-c-replacement.md` |
| What | Ready-made board inside each fan presses its keys and joins the WiFi | Ready-made board near each fan presses its keys; an ESP32 beside it carries the presses over WiFi | Ready-made board next to the Pi presses the fan's keys through its wall-control jacks | ESP32 at each fan sends complete-state packets on the infrared receiver line | ESP32 at each fan replaces the MaxxFan board |
| Building | **None** | Four short wires, a 12 → 5 V converter, flash the ESP32 | **None**: buy, plug, four jumper wires | ESP32 + diode on perfboard, 3 solder joints per fan | Perfboard with motor drivers, a weekend per fan |
| Cables through the van | **None** | **None** | 2 or 4 runs to the roof | None | None |
| Work at the fan | Short RJ45 lead, fan's 12 V through the board | Short RJ45 lead (and RJ11 if fitted), 12 V for the ESP32 | Plug in a cable or two | Open trim, solder to the receiver | Swap the board |
| Commands | Key presses, made by the controller from absolute MQTT values; lid is a toggle | Key presses decided on the Pi (toggles, steps); RJ11 adds absolute Off / Open / Close | Key presses (toggles, steps); RJ11 adds absolute Off / Open / Close | Absolute state in one packet | Absolute |
| What the screen knows | On/off, speed and auto reported by the controller. Direction its guess. Lid believed | Auto mode sensed. With RJ11: on/off and lid right after every touch. Speed and direction believed | Same as E | Own commands and the handheld remote | Everything |
| Setpoint control | No | No | No | Yes | Yes |
| Works if the Pi or link dies | Yes | Yes, fans behave as stock | Yes | Yes | No |
| Needs | WiFi that is always on | WiFi that is always on | Nothing extra | WiFi | WiFi |
| Cost for two fans | ~€50 plus shipping | ~€40 boards + ~€35 ESP32s, converters, cables | ~€20 for one board or ~€40 for two, plus shipping | ~€30 | ~€110 |

## Why A sends packets instead of pressing keys

The infrared remote sends the complete desired state in one 16-byte packet, which on the
receiver's output pin is a plain 1200-baud serial frame. Wiring the ESP32 there gives absolute
commands and lets it hear the handheld remote. Key pressing, which is what options E, V and W do,
is relative: without knowing the current state the driver cannot set "exhaust 60 %" directly,
and every step beeps. W's controller hides most of that by sensing the fan's current.

## Why WiFi + MQTT for options E, W, A and C

Each fan already has 12 V, so WiFi means no data cable to the roof, Venus OS has an MQTT broker
built in, and both VanTurtle's WiFi firmware and ESPHome speak MQTT. If WiFi drops, the fans
keep working from their keypad and remote. Option V needs none of this: the Pi talks to the
board directly. Option E is option V with the I2C wires replaced by WiFi: the ESP32 at each
fan presses one key per message and confirms it (`docs/mqtt-contract.md`).

## Assumptions specific to these options

| Assumption | Source | Risk if wrong |
|---|---|---|
| Option E: VanTurtle board needs no 12 V of its own; its fan side runs from the fan through the cable | VanTurtle documents only VCC, GND, SDA, SCL; "9–14 V from the fan" | Option E: add a fused 12 V feed as VanTurtle says |
| Option E: The ESP32's own pull-ups suffice at 50 kHz with wires under 20 cm | VanTurtle's ESP32 library uses them too | Bridge the PUR pads (safe at 3.3 V) |
| Option E: The board's "tiny bit of heat" is fine in a vented box near the fan | VanTurtle warns only against enclosed spaces like a ceiling | Move the box to open air |
| Option E: ESP32-C3 holds the van WiFi | Common; some SuperMini batches are weak | `output_power: 8.5dB` or another board |
| `dtparam=i2c_arm=on` in `/u-boot/config.txt` enables I2C on Venus OS for the Pi | Victron community posts | Option V: find the current way for your Venus version |
| VanTurtle register map, key bits, timings | VanTurtle documentation and its own libraries | Options V and E: adjust constants in `vanturtle.py` |
| Infrared packet layout and 834 µs symbol time (option A) | `dbus-maxxfan` project | Packets ignored |
| Keypad matrix and lid motor currents (option C) | Community pinouts, Minuet project | Remap and retune on the bench |

## Sources for these options

- [VanTurtle DIY MaxxFan controller](https://vanturtle.com/control-a-maxxfan-deluxe-with-raspberry-pi-or-esp32/), its
  [protocol documentation](https://vanturtle.com/vtafc-docs/communicating-with-the-fan-controller/) and
  [libraries](https://vanturtle.com/vtafc-docs/integrating-your-microcontroller/): options V and E.
- [dbus-maxxfan](https://github.com/mcgyver78/dbus-maxxfan): infrared packet format (option A).
- [Minuet](https://github.com/brown-studios/minuet): open-hardware replacement MaxxFan controller (option C).
- [zef.studio MaxxFan notes](https://zef.studio/projects/maxxfan/): wall-control jack pin pairs.
