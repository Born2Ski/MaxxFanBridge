> **Archived:** not part of the final setup (VanTurtle Smart Controllers over WiFi). See
> `archive/README.md` for what moved where.

# Option A — Tap board (keeps the MaxxFan controller)

An ESP32 sits in the ceiling trim of each fan, powered from the fan's 12 V feed, and shares
the output pin of the fan's infrared receiver with the fan's own controller.

## How it works

The MaxxFan remote sends a 16-byte packet holding the complete state. On the air it is a
38 kHz carrier; after the fan's receiver removes the carrier, what reaches the fan's
controller is an ordinary serial frame:

- 1200 baud (834 µs per bit), 8 data bits, LSB first, 2 stop bits, idle high
- The receiver output is open-collector with a weak pull-up, so a second device can pull it low

So the ESP32 UART, through one diode, can *write* packets onto that line as if the remote had
sent them, and can *read* everything the real remote sends.

```
 byte 0-9   5A A5 80 7F 40 BF 20 DF 10 CC      fixed preamble
 byte 10    state bits: 01 fan on, 02 special, 04 exhaust, 08 lid open, 10 auto, 20 beep twice
 byte 11    speed 0-100, steps of 10
 byte 12    setpoint in °F = trunc(°C × 1.8) + 32
 byte 13    FF
 byte 14    23
 byte 15    XOR of bytes 10-14
```
"Special" is set in auto mode and when the fan runs with the lid closed (ceiling-fan mode).

## Parts (per fan)

| Qty | Part | Notes |
|---|---|---|
| 1 | ESP32 DevKit (ESP32-WROOM-32, 30-pin) | Any classic ESP32 dev board |
| 1 | 12 V → 5 V buck module, ≥ 500 mA | Pololu D24V5F5, or an MP1584 mini module set to 5.0 V *before* connecting |
| 1 | Inline fuse holder + 1 A fuse | On the 12 V tap |
| 1 | Schottky diode BAT43 (or 1N5817) | Lets the ESP32 only pull the line low |
| 1 | 47 kΩ resistor | Read-side protection |
| 1 | Small perfboard, 3 thin wires, heat-shrink | |
| | *Optional motor sensing:* 4× 47 kΩ, 4× 10 kΩ, 4× 1 µF | See "Stage 2" |
| | *Optional no-solder variant:* 940 nm IR LED, 100 Ω, TSOP38238 | See "LED variant" |

## Wiring

```
 Fan 12 V + ──[1 A fuse]── buck IN+        buck OUT+ (5 V) ── ESP32 5V / VIN
 Fan 12 V − ────────────── buck IN−        buck OUT−       ── ESP32 GND ── fan board GND

                         BAT43
 ESP32 GPIO17 (TX) ──────|<|──────┬────── fan IR receiver OUT pin
                    (cathode to   │
                     the ESP32)   │
 ESP32 GPIO16 (RX) ───[47 kΩ]─────┘
```

- The diode's striped end (cathode) faces the ESP32. The ESP32 can then only pull the line
  low and never pushes 3.3 V into the fan's logic.
- The 47 kΩ keeps the ESP32 input safe if the fan's logic runs at 5 V.
- Ground must be common: the buck converter's minus is the fan's supply minus, which is fine.

### Finding the receiver pin

The receiver is the small 3-legged part behind the dark window of the ceiling keypad.
With the fan powered and a multimeter (black lead on supply minus):

1. One leg reads 0 V: ground.
2. One leg reads a steady 3.3 V or 5 V: supply. Note which; it does not change the circuit.
3. The third reads nearly the same as supply and dips slightly while you hold a remote
   button pointed at it: that is OUT. Solder the tap wire here.

## Bench checks before closing the trim

1. With only the RX side connected, flash the firmware and watch the log while pressing
   remote buttons. You should see 16-byte packets starting `5A A5 80 7F`. If the bytes are
   garbage, note them; the baud rate may need a small trim (`baud_rate: 1199`…`1205`).
2. Connect the TX diode. Publish `maxxfan/fan1/set/lid` = `1`. The lid should open and the fan beep.
3. Press keys on the handheld remote and confirm `maxxfan/fan1/state/#` follows.
4. Check that the handheld remote still works with the ESP32 unpowered.

## Limits of this option

- **Ceiling keypad presses are invisible** to the node, so the touchscreen can show a stale
  state after someone uses the keypad. The node re-sends its state only on command, never on
  its own, so it will not fight the keypad. Stage 2 closes most of this gap.
- The fan beeps on each packet, as it does with the remote.
- Thermostat behaviour is the MaxxFan's own. The node only sets mode and setpoint.
- Both fans accept the same packets, which is exactly why this is wired: each node reaches
  only its own fan. (With LEDs in open air, one emitter could command both fans.)

## Stage 2 (optional) — sensing the real state

Four voltage dividers let the ESP32 see what the motors are actually doing, which catches
keypad presses.

```
 motor lead ──[47 kΩ]──┬──── ESP32 ADC pin
                       ├──[10 kΩ]── GND
                       └──[1 µF]─── GND
```

| Signal | ESP32 pin |
|---|---|
| Fan motor lead 1 (black) | GPIO34 |
| Fan motor lead 2 (white) | GPIO35 |
| Lid motor lead 1 | GPIO32 |
| Lid motor lead 2 | GPIO33 |

16 V on a lead gives 2.8 V at the pin. Community reports say that one fan lead sits at
supply voltage and the other drops with speed, which lead depending on direction. I have not
seen this measured on a 7000K, so the firmware only publishes the four voltages under
`maxxfan/<id>/diag/` for now. Record them for off, each direction, three speeds and lid
moving each way, and the reconciliation logic can then be written against real numbers.

## LED variant (no soldering at all)

Same firmware. Instead of the diode tap, an IR LED and a receiver sit at the keypad window:

```
 ESP32 GPIO18 (38 kHz carrier) ──[100 Ω]──►|── ESP32 GPIO17 (TX)      LED lights only while
                                    IR LED                            TX is low and carrier high
 TSOP38238: OUT → GPIO16,  VS → 3V3,  GND → GND
```

Enable the `carrier` output block in `firmware/option-a.yaml`. Range is a few centimetres,
which is the point: tape the LED to the window so it does not reach the other fan.

## Fallback — key emulation on the wall-control jack

If packets by wire do not work on your board revision, the RJ-45 jack on the fan board takes
key presses as contact closures between pin pairs (pin 1 at left, latch down):

| Key | Pins |
|---|---|
| Speed up | 6 + 8 |
| Speed down | 5 + 8 |
| Auto | 4 + 7 |
| In / Out | 5 + 7 |
| On / Off | 6 + 7 |
| Lid (7000K / 7500K) | Up and Down together |

Use one optocoupler or small reed relay per key; plain transistors to ground do not work
because the pins form a scanned matrix. Other community pinouts differ, so confirm each pair
with a jumper wire first. This route gives relative commands only and needs Stage 2 sensing
to be usable from a touchscreen, which is why it is not the main design.
