> **Archived:** not part of the final setup (VanTurtle Smart Controllers over WiFi). See
> `archive/README.md` for what moved where.

# MQTT contract between an ESP32 fan node and the Venus driver

Broker: the one built into Venus OS (port 1883). Options A and C use this contract. Option V
talks I2C; option W uses the VanTurtle controller's own topic layout under `maxxfan/<id>/vt/`
(see `hardware/option-w-vanturtle-wifi.md` and `vtwifi.py`); option E relays single key
presses under `maxxfan/<id>/board/` ([below](#option-e-key-press-relay)).
`<id>` is the node id, e.g. `fan1`, `fan2`.
All payloads are short plain-text scalars so they can be watched and poked with
`mosquitto_sub -t 'maxxfan/#' -v` and `mosquitto_pub`.

## Node → Venus (all retained)

| Topic | Payload | Meaning |
|---|---|---|
| `maxxfan/<id>/status` | `online` / `offline` | Birth and last-will message |
| `maxxfan/<id>/state/on` | `0` / `1` | Fan motor running |
| `maxxfan/<id>/state/speed` | `10`…`100`, step 10 | Speed in percent (kept while off) |
| `maxxfan/<id>/state/dir` | `0` intake / `1` exhaust | Air direction |
| `maxxfan/<id>/state/lid` | `0` closed / `1` open | Lid target position |
| `maxxfan/<id>/state/mode` | `0` manual / `1` auto | Thermostat mode |
| `maxxfan/<id>/state/setpoint` | `-2`…`37` | Thermostat setpoint, whole °C |
| `maxxfan/<id>/state/temp` | e.g. `23.4` | Ceiling temperature, °C. Option C only |
| `maxxfan/<id>/state/variant` | `A` / `C` | Hardware variant, for information |

## Venus → node (not retained)

| Topic | Payload |
|---|---|
| `maxxfan/<id>/set/on` | `0` / `1` |
| `maxxfan/<id>/set/speed` | `10`…`100` |
| `maxxfan/<id>/set/dir` | `0` / `1` |
| `maxxfan/<id>/set/lid` | `0` / `1` |
| `maxxfan/<id>/set/mode` | `0` / `1` |
| `maxxfan/<id>/set/setpoint` | `-2`…`37` |

## Rules

- The node is the owner of the state. The driver never assumes a command worked; it shows
  what the node publishes back. A command the node accepts is echoed on the matching
  `state/` topic within about a second.
- The node republishes all `state/` topics on connect and whenever anything changes,
  whatever the cause (touchscreen, handheld remote, keypad, thermostat).
- Commands are not retained, so a node that reboots does not replay an old command.
- Anything else under `maxxfan/<id>/diag/` is free-form diagnostics and ignored by the driver.

## Option E: key-press relay

The ESP32 beside each VanTurtle board (`firmware/vanturtle-board.yaml`) knows nothing about
fans. It presses the key it is told to and reports the board's auto-sense inputs. All fan
logic stays in the driver (`vtboard.py`, `vanturtle.py`). Payloads are JSON.

| Topic | Direction | Payload |
|---|---|---|
| `maxxfan/<id>/board/press` | Venus → ESP32, QoS 0 | `{"seq":17,"ch":1,"key":16,"ms":750,"gap":250}` |
| `maxxfan/<id>/board/done` | ESP32 → Venus | `{"seq":17,"ok":true,"i2c":true,"in1":255,"in2":255}` |
| `maxxfan/<id>/board/state` | ESP32 → Venus, retained | `{"in1":255,"in2":255,"i2c":true}`, every 10 s and on change |
| `maxxfan/<id>/board/status` | ESP32 → Venus, retained | `online` / `offline` (birth and last will) |

- `ch` is the board port (1 = FAN ONE, 2 = FAN TWO). `key` is the port's output bits as in
  VanTurtle's register map: bit 0 must stay 0 (auto-sense input), bit 1 (activity LED) is added
  by the ESP32. Holds of 50–2000 ms, gaps up to 2000 ms; anything else is refused with
  `"ok":false,"err":"bad"`.
- The ESP32 holds the key for `ms`, releases it, waits `gap`, reads both input registers and
  answers on `done`. `ok` means the key went down and came up again; `i2c` false means the
  inputs could not be read afterwards (`in1`/`in2` are then left out).
- One press at a time; a different `seq` while busy gets `"err":"busy"`.
- **The same `seq` twice is one press.** The ESP32 remembers the answers to its last four key
  presses and repeats the answer instead of pressing again. The driver resends a press with
  the same `seq` when no answer comes, so a lost answer never becomes a second press. Beeps
  (`key` 128) are not remembered: a second beep does no harm.
- `in1` / `in2`: input registers of ports 1 and 2. Bit 0 = 0 means the fan's Auto light is on.
- Commands go out with QoS 0 and are not retained, so a press is never delivered late, after
  the driver has given up on it.
- The driver shows a card as disconnected on `offline`, after 35 s without `state` or `done`,
  or while `i2c` is false.

Try it by hand on the Venus device, with the driver stopped:

```sh
mosquitto_sub -v -t 'maxxfan/fan1/board/#' &
mosquitto_pub -t maxxfan/fan1/board/press -m '{"seq":1,"ch":1,"key":128,"ms":150,"gap":250}'   # beep
```
