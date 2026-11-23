> **Archived:** not part of the final setup (VanTurtle Smart Controllers over WiFi). See
> `archive/README.md` for what moved where.

# Option C — Replacement controller

The MaxxFan control board is unplugged and kept as a spare. An ESP32 with two motor driver
modules takes over the fan motor, the lid motor, the thermistor and the ceiling keypad.
Everything plugs into the fan's existing connectors, so going back to stock is a matter of
plugging the original board in again.

## What the node must do itself

| Function | Stock board | Here |
|---|---|---|
| Fan motor, 10 speeds, two directions | Yes | PWM driver, soft start, pause before reversing |
| Lid open / close with end detection | Yes | Driver with current sensing; stall = end of travel |
| Ceiling keypad | Yes | Scanned by the ESP32 |
| Handheld infrared remote | Yes | Own receiver behind the keypad window, same packet decoder as option A |
| Thermostat (auto mode) | Yes | In firmware, using the original 10 kΩ sensor |
| Beeper | Yes | Left out in v1 (optional piezo on GPIO14) |
| Works without WiFi / Venus | Yes | Yes: keypad, remote and thermostat are local |

## Parts (per fan)

| Qty | Part | Notes |
|---|---|---|
| 1 | ESP32 DevKit (ESP32-WROOM-32, 30-pin) | |
| 1 | Cytron MD13S motor driver | Fan motor. 13 A continuous, PWM + DIR inputs, 20 kHz capable. Generous on purpose: stays cold in a hot roof |
| 1 | Pololu DRV8876 carrier (#4036) | Lid motor. Has a current-sense output for end-of-travel detection |
| 1 | 12 V → 5 V buck, ≥ 1 A | Pololu D24V10F5 or similar |
| 1 | TSOP38238 infrared receiver | Mounted behind the keypad window |
| 1 | 10 kΩ 1 % resistor | Thermistor divider |
| 2 | 47 kΩ + 10 kΩ | Supply voltage divider |
| 1 | TVS diode SMBJ18A (or 1.5KE18A) + 470 µF 25 V capacitor | Across the 12 V input, vehicle transients |
| 1 | 1×8 pin header, 2.54 mm, long pins | Keypad flex cable plugs onto it |
| | Connectors to match the fan: 2-pin for lid motor, 2-pin for thermistor, spade or ferrules for motor and power | Measure on your fan before ordering |
| 1 | Perfboard about 50 × 70 mm, stand-offs | Fits where the OEM board was |

Keep the fan's existing 5 A fuse on the 12 V feed.

## Pin map

| ESP32 pin | Goes to | Purpose |
|---|---|---|
| GPIO25 | MD13S `PWM` | Fan speed, 20 kHz |
| GPIO26 | MD13S `DIR` | Fan direction |
| GPIO32 | DRV8876 `EN` | Lid motor run |
| GPIO33 | DRV8876 `PH` | Lid motor direction |
| GPIO27 | DRV8876 `SLP` | Wake the driver (high = awake) |
| GPIO34 | DRV8876 `CS` | Lid motor current, about 2.5 V per amp |
| GPIO36 | Thermistor divider | 3V3 ─[10 kΩ]─●─[thermistor]─ GND, tap at ● |
| GPIO39 | Supply divider | 12 V ─[47 kΩ]─●─[10 kΩ]─ GND |
| GPIO16 | TSOP38238 `OUT` | Handheld remote (UART RX, 1200 baud) |
| GPIO18, GPIO19 | Keypad rows | Header pins 7, 8 |
| GPIO21, GPIO22, GPIO23 | Keypad columns | Header pins 4, 5, 6 |
| GPIO14 | Piezo (optional) | |
| 5V, GND | Buck output | |

Driver power: MD13S `VIN` and DRV8876 `VIN` to fused 12 V; all grounds common. Leave the
DRV8876 `PMODE` pin unconnected or low so `EN`/`PH` control applies (check the carrier's
page; Pololu ships it this way).

## Wiring overview

```
 12 V + ─[5 A fuse]─┬─ TVS + 470 µF to GND
                    ├─ MD13S VIN ────────── fan motor (2 wires)
                    ├─ DRV8876 VIN ──────── lid motor (2 wires)
                    └─ buck ─ 5 V ───────── ESP32
 Thermistor (2 wires) ── divider ── GPIO36
 Keypad flex (8 pins) ── header ─── GPIO18/19/21/22/23
 TSOP38238 ───────────────────────── GPIO16
```

## Keypad

Community measurements on the wall-control jack give these pairs, and the keypad header is
believed to carry the same matrix:

| Key | Row pin | Column pin |
|---|---|---|
| On / Off | 7 | 6 |
| In / Out | 7 | 5 |
| Auto | 7 | 4 |
| Speed up | 8 | 6 |
| Speed down | 8 | 5 |
| Lid open / close (if your keypad has it) | 8 | 4 |

Pins 1 and 3 are reported to be the indicator LED. **Verify before wiring:** unplug the flex,
set a multimeter to continuity, and press each key while probing pin pairs. Write down the
real table and adjust `rows`, `columns` and `keys` in `firmware/option-c.yaml`.

## Bench tuning (do this with the fan on a table or with the lid watched)

1. **Lid current.** Run the lid each way from the ESPHome web log. Note the running current
   and the current when it reaches the end. Set `*_moving_current_threshold` between zero and
   running, and `*_obstacle_current_threshold` between running and stalled. The Minuet project
   found about 1.2 A a good trip level for this lid motor.
2. **Lid time.** Time a full open and close; set `open_duration` / `close_duration` and make
   `max_duration` a few seconds longer. This is the safety net if current sensing misses.
3. **Fan direction.** If "exhaust" blows in, swap the two fan motor wires.
4. **Fan current.** With the fan at 100 % check the MD13S and wiring stay cool; the stock
   motor draws roughly 4–5 A at full speed.
5. **Thermistor.** Compare the reported temperature with a thermometer; adjust `b_constant`
   (3950 is the value reported for the built-in sensor).

## Safety behaviour built into the firmware

- The fan stops and waits 3 s before changing direction.
- Lid drive is cut by stall current or by timeout, whichever comes first.
- On boot nothing moves: the fan stays off and the lid is left where it is until a command.
- Losing WiFi changes nothing locally.

## Alternative: a ready-made board

[Minuet](https://github.com/brown-studios/minuet) is an open-hardware board that does this
job as a drop-in, with a brushless motor swap that makes the fan much quieter. It runs
ESPHome on an ESP32-C3, so it could publish the same topics as this node and use the same
Venus driver. Kits were "being planned" when I checked; worth a look before building C.
