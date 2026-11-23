> **Archived:** not part of the final setup (VanTurtle Smart Controllers over WiFi). See
> `archive/README.md` for what moved where.

# Option E — VanTurtle DIY board + ESP32 at each fan, over WiFi

An alternative to option W for someone with VanTurtle's
[DIY MaxxFan controller](https://vanturtle.com/control-a-maxxfan-deluxe-with-raspberry-pi-or-esp32/)
rather than the Smart Controller: one board per fan. Each board sits near its fan and presses
the fan's keys through the wall-control jack, exactly like a wired wall control. The DIY board
has no WiFi and no processor of its own, so a small ESP32 board sits beside it, joins the
van's WiFi and passes on key presses from the Pi. Its main advantage over option W: with an
RJ11 cable as well, on/off and the lid are absolute.

The ESP32 makes no decisions. The driver on the Pi decides which keys to press and keeps track
of what the fan is doing, with the same tested code as a board wired to the Pi's own pins
(option V). Only the last metre is different: the presses travel over WiFi.

```
 Fan 1 ── short RJ45 lead ── VanTurtle board ── 4 short wires ── ESP32-C3 ─┐
                             (port FAN ONE)                      12 → 5 V  │
                                                                           │  WiFi, 2.4 GHz
 Fan 2 ── short RJ45 lead ── VanTurtle board ── 4 short wires ── ESP32-C3 ─┤
                                                                           │
                                                 van WiFi router ──────────┴── Raspberry Pi, Venus OS
                                                                               MQTT broker (port 1883)
                                                                               dbus-maxxfan-bridge
                                                                               gui-v2 cards
```

No cable runs from the fans to the Pi. Each fan keeps working from its keypad and remote if
the Pi, the WiFi or an ESP32 stops.

## What the screen knows

The fan reports only one thing back through the board: whether its Auto light is on.
Everything else the driver shows is what it *believes*, from the keys it pressed. A belief
is right until someone uses the ceiling keypad or the handheld remote.

| Control | RJ45 cable only | RJ45 + RJ11 cable to the same fan |
|---|---|---|
| Mode (Manual/Auto) | **Sensed** from the Auto light | **Sensed** |
| On / off | Believed (On/Off is a toggle) | **Right after every touch** (Off is absolute) |
| Lid | Believed (open/close is a toggle) | **Right after every touch** (Open and Close are absolute) |
| Speed | Believed; choosing 10 % always re-homes | Same |
| Direction | Believed | Same |
| Auto setpoint | Not offered: keys can only nudge it | Not offered |

## First: which jacks

VanTurtle fits the jacks you choose when ordering. Check which ones each board has:

| Board has | Use | `config.ini` |
|---|---|---|
| One RJ45 jack, on port FAN ONE | That jack | `rj45 = 1` (the default) |
| Two RJ45 jacks | FAN ONE; the second stays free | `rj45 = 1` |
| RJ45 on FAN ONE and RJ11 (6-pin) on FAN TWO | Both, to the **same** fan | `rj45 = 1`, `rj11 = 2` |

The RJ11 cable is worth having: closing the lid when it starts to rain, or switching off when
you leave, then always works from the screen, whatever was pressed on the keypad before.
VanTurtle: "Deluxe fans can actually use both types of ports at the same time." If port FAN
TWO is empty, ask VanTurtle whether they can fit an RJ11 jack there. You can add it later: plug
in the cable, set `rj11 = 2`, restart the driver.

Also check whether the boards have **screw terminals** for VCC, GND, SDA and SCL, or bare pads.
Screw terminals with ferrules survive rough roads better than jumper wires.

## Parts to buy

| Qty | Part | Notes |
|---|---|---|
| 2 | ESP32-C3 board with pins, e.g. **Espressif ESP32-C3-DevKitM-1** or **LOLIN C3 Mini** | €5–10 each. The tiny "C3 SuperMini" (€3) also works, but some batches have weak WiFi |
| 2 | 12 V → 5 V converter, hard-wired, 1 A or more, input rated to at least 24 V | A sealed 12 V-to-USB-C module (then power the ESP32 by its USB socket), or a small regulator such as Pololu D24V10F5 |
| 2 | Inline fuse holder with a 1 A fuse | One per converter |
| 2 | Network cable with **short-body RJ45 plug**, all 8 conductors (PoE-rated is a safe pick), under 10 m | VanTurtle: a normal plug can snap the fan's jack off when the fan is lowered |
| 2 | 6-wire (6P6C) phone cable, under 10 m | Only if you use RJ11 |
| 8 | Jumper wires 10–20 cm, female ends; or wire with bootlace ferrules for screw terminals | |
| 2 | Small plastic box with ventilation holes, about 100 × 70 × 40 mm | Plastic, so WiFi gets out |
| | Screws or a cable-tie base, hot glue | To fix the boards and the plug-on wires |

About €30–40 for both fans, on top of the boards.

## Where to put it

- **Near the fan, but not inside the ceiling cavity.** VanTurtle: "the controller generates a
  tiny bit of heat, so do not mount it in an enclosed space like a ceiling." A vented box in an
  overhead cupboard, or on the ceiling panel beside the fan's trim, is fine.
- The RJ45 cable runs from the box to the wall-control jack on the fan's circuit board, inside
  the roof unit, the way a wall control's cable would. Plug it in **before** lowering the fan
  back into the roof opening, and check that no wire gets pinched.
- Not inside a metal cabinet, or the WiFi will suffer.
- Fix both boards with screws or cable ties; sticky pads and Velcro "might not survive the
  next non-paved road" (VanTurtle).

## Wiring

**Pull the fan's fuse first.**

```
 Power
   12 V from a fused circuit nearby (the fan's own feed is closest)
        ── 1 A inline fuse ── converter IN+
   van negative ───────────── converter IN−
   converter 5 V out ──────── ESP32 5V pin (or its USB-C socket)
   converter GND out ──────── ESP32 GND

 ESP32-C3                VanTurtle board (screw terminals or header)
   3V3   ──────────────  VCC     3.3 V, never 5 V: the ESP32's pins are not 5 V tolerant
   GND   ──────────────  GND
   GPIO4 ──────────────  SDA
   GPIO5 ──────────────  SCL

 Board port FAN ONE ──── RJ45 lead ──── the fan's RJ45 wall-control jack
 Board port FAN TWO ──── RJ11 lead ──── the same fan's RJ11 jack (if you use it)
```

- Keep the four wires between ESP32 and board short, 20 cm at most.
- **Address pads:** leave all open on both boards (address 0x27). Each board has its own ESP32.
- **PUR pads:** leave open at first. The firmware uses the ESP32's own weak pull-ups at a slow
  bus speed. If the start-up log (below) does not find the board reliably, bridge the two PUR
  pads with solder. That is safe here because VCC is 3.3 V.
- VanTurtle documents no 12 V connection on the board itself: its fan side runs from the fan
  through the cable, its logic from VCC.
- Other ESP32 boards work too; set `sda_pin` and `scl_pin` at the top of
  `firmware/vanturtle-board.yaml` to the pins you used.
- The ESP32 draws about 0.4 W, always: roughly 10 Wh per day each from the house battery.

## Flash the ESP32s (at home, before fitting)

1. Install ESPHome on a computer (`pip install esphome`).
2. In `firmware/`, copy `secrets.yaml.example` to `secrets.yaml` and fill in the van WiFi name
   and password, the Pi's fixed address (`mqtt_broker`), an update password, and the MQTT login
   if you need one (next section).
3. ESP32 number 1 on USB: `esphome run vanturtle-board.yaml`, pick the USB port. Label it *fan 1*.
4. ESP32 number 2: `esphome -s node_id fan2 run vanturtle-board.yaml`. Label it *fan 2*.
5. Later updates go over WiFi with the same commands.

If it cannot join the WiFi (new router, new password), the ESP32 opens its own network
`maxxfan-board-fan1` after a minute; join it with a phone, using the update password, and enter
the new WiFi there.

## The network and Venus OS

The same as for any WiFi device at the fans. In short:

- The Pi and both ESP32s on the **same 2.4 GHz WiFi**; the Pi with a **fixed address**.
- *Settings → Integrations → MQTT Access → on.*
- The Venus OS security profile decides whether devices on the WiFi may use MQTT on port
  1883, and with which password. Try in this order; stop at the first that works (the card
  comes online):
  1. Keep your profile. Set `mqtt_username` to any name and `mqtt_password` to the security
     profile password (the one Remote Console asks for), and flash again.
  2. Profile **Weak**, with that password.
  3. Profile **Unsecured**, both left empty. Acceptable only on a private WPA2 WiFi.

  Details and the reasons: "Venus OS: let the controllers into the broker" in
  `option-w-vanturtle-wifi.md`.

## Bench checks

**On the table**, ESP32 and board on the computer's USB, no fan yet:

```sh
esphome logs vanturtle-board.yaml      # pick the USB port
```

The log should show the I2C scan finding `0x27`, then the MQTT connection. On the Pi (by SSH):

```sh
mosquitto_sub -v -t 'maxxfan/#'
```

`maxxfan/fan1/board/status online`, then a `state` line every 10 seconds with `"i2c":true`.
The ESP32's log lines also arrive there (`maxxfan/fan1/board/log`), which is the easy way to
watch it once it is fitted.

**With the fan connected**, stop the driver (`svc -d /service/dbus-maxxfan-bridge`) and keep
`mosquitto_sub` running in one shell. In another:

```sh
n=$(date +%s)   # each press needs a new number; the ESP32 ignores a number it has just seen
p() { n=$((n+1)); mosquitto_pub -t maxxfan/fan1/board/press -m "{\"seq\":$n,\"ch\":$1,\"key\":$2,\"ms\":${3:-150},\"gap\":250}"; sleep 1; }

p 1 128          # Beep: the fan beeps, and a "done" line with "ok":true comes back
p 1 16 750       # On/Off
p 1 32           # Faster
p 1 64           # Slower
p 1 8            # In/Out
p 1 96           # Faster+Slower: does the lid open/close on your 7000K/7500K?
p 1 4            # Auto: "in1" in the answer turns even (bit 0 = 0) while Auto is on
p 1 4            # Auto off again
p 2 64           # RJ11 Off (only with the RJ11 cable on port 2): does it also close the lid?
p 2 32           # RJ11 Open
p 2 16           # RJ11 Close
```

For fan 2, use `maxxfan/fan2/board/press`. Each `done` line should come back within a second
or so of the key being released.

Write down, and put the answers in `config.ini` under both fans:

| Question | Setting |
|---|---|
| Does RJ11 Off also close the lid? | `rj11_off_closes_lid = yes` or `no` |
| Does On/Off (RJ45) open a closed lid by itself? | `on_opens_lid = yes` or `no` |
| How long is a full lid stroke (time an open and a close)? Add 2 s | `lid_settle_s` |
| Does On/Off need the 0.75 s hold, or does `p 1 16` (0.15 s) work? | `onoff_press_s` |
| Is a single key after a few minutes of quiet sometimes ignored? If never, save a beep per command | `wake_beep = no` |

Until the first two are answered, the driver assumes either key might move the lid and waits
for a full stroke before the next lid key, so some commands take up to 25 s.

Start the driver again with `svc -u /service/dbus-maxxfan-bridge`.

## What the driver does

- **At start it presses nothing.** It reads the Auto light and restores its last belief from
  `state-<fan>.json`, so a Venus reboot does not disturb running fans.
- A touch on the screen updates the card at once; the presses follow one at a time, so
  dragging the speed slider does not queue up dozens of steps.
- Each press goes to the ESP32 with a number and is answered after the key is released. If
  the answer does not come within about 2 seconds, the same press is sent again with the same
  number. The ESP32 recognises the number and only answers, so a lost message never turns into
  a second press. After three tries the card shows disconnected; the driver tries again every
  10 seconds, and when it wants that same key again it reuses the number.
- Before a burst of presses after a quiet spell it sends one **Beep**, because a sleeping fan
  swallows its first key.
- It never keys the lid while it may still be moving (`lid_settle_s`).
- Touching a manual control while the fan is in Auto first leaves Auto.
- Auto pressed on the keypad or remote shows on the card within a second or two.
- The card shows **disconnected** when the ESP32 drops off the WiFi (at once if the broker
  notices, at the latest after 35 seconds without its heartbeat), when the ESP32 reports it
  cannot reach the board, or when the Pi's own broker connection is lost.

## When the screen and the fan disagree

This only happens after someone uses the ceiling keypad or the handheld remote. The screen can
only send a value different from the one it shows, so the fix is often "away and back".

| Wrong on screen | Fix |
|---|---|
| On/off or lid, with RJ11 | Tap the control: the fan follows the card. Tap again if you wanted the other state |
| On/off or lid, RJ45 only | Press the matching key on the ceiling keypad once, so the fan matches the card |
| Speed | Slide to 10 % (if it already shows 10 %, go up a step first), then to the speed you want |
| Direction | Press In/Out on the ceiling keypad once |

## Limits of this option

- On/off (RJ45 only), lid (RJ45 only), speed and direction are believed, not known.
- Needs WiFi that is always on. When it drops, the cards show disconnected and the fans work
  from their keypads and remotes as usual.
- If an ESP32 restarts during a WiFi outage, it forgets which presses it already made, and one
  press may be repeated. The driver cannot see that; fix it as in the table above.
- The fan beeps on every key, as with its own keypad. Changing speed from 20 % to 70 % is five
  beeps, plus one wake beep.
