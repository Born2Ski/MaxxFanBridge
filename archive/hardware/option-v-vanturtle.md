> **Archived:** not part of the final setup (VanTurtle Smart Controllers over WiFi). See
> `archive/README.md` for what moved where.

# Option V — VanTurtle board on the Venus Pi (no hardware to build)

A ready-made [VanTurtle MaxxFan controller](https://vanturtle.com/control-a-maxxfan-deluxe-with-raspberry-pi-or-esp32/)
sits next to the Raspberry Pi that runs Venus OS and is wired to its I2C pins. Network and
phone cables run from the board to the wall-control jacks on each fan's circuit board. Nothing
is soldered and nothing is mounted at the fans.

The board presses keys electrically, exactly like a wired wall control. The fan reports back
only whether auto mode is on. Everything else the driver shows is what it *believes*, based
on the keys it pressed. How much of that belief can be trusted depends on which jacks you use.

## One board or two

Each board has two channels, one cable each. The fans have two jacks, with different keys:

| Jack | Keys | Kind |
|---|---|---|
| RJ45 | On/Off, In/Out, Faster, Slower, Auto, Beep, Faster+Slower = lid open/close | Toggles and steps |
| RJ11 (6-pin) | Off, Open lid, Close lid, On/next speed | Absolute |

| | **One board, RJ45 only** | **Two boards, RJ45 + RJ11** (recommended) |
|---|---|---|
| Cost | ~€20 + shipping | ~€40 + shipping |
| Cables to the roof | 2 (one per fan) | 4 (two per fan) |
| Auto mode | Real, sensed | Real, sensed |
| On / off | Toggled from belief: wrong if the keypad or remote was used | **Always right after a touch** (Off is absolute, On is toggled from a known Off) |
| Lid | Toggled from belief: same caveat | **Always right after a touch** |
| Speed | Stepped from belief; **10 % always re-homes** | Same |
| Direction | Toggled from belief | Toggled from belief |
| Setpoint | Not offered (keys only nudge it) | Not offered |

On/off and the lid are what matter most from a touchscreen (closing up when it rains, or
when you leave), so I recommend two boards. You can start with one and add the second later:
plug in the RJ11 cables, uncomment the two `rj11 =` lines in `config.ini`, and restart.

When ordering, ask for **board 1 with two RJ45 jacks** and **board 2 with two RJ11 (6P6C)
jacks**. VanTurtle offers custom connectors.

## Parts

| Qty | Part |
|---|---|
| 1 or 2 | VanTurtle MaxxFan controller (DIY board) |
| 2 | Network cable, all 8 conductors (PoE-rated is a safe pick), **short-body plug** at the fan end, under 10 m |
| 2 (option) | 6-wire phone cable (6P6C), under 10 m |
| 4 | Female-female jumper wires, short (I2C does not like long leads; keep the board within ~30 cm of the Pi) |

The wall-control jacks sit on the fan's board inside the roof unit. VanTurtle warns that a
normal-length plug can snap the RJ45 jack off when the fan is lowered back into place.

## Wiring

```
 Raspberry Pi 3B header               VanTurtle board(s)
 pin 1  3V3  ───────────────────────  VCC       (3.3 V, never 5 V: the Pi's I2C pins are not 5 V tolerant)
 pin 3  GPIO2 / SDA ────────────────  SDA
 pin 5  GPIO3 / SCL ────────────────  SCL
 pin 9  GND  ───────────────────────  GND       (any ground pin: 6, 9, 14, 20, 25, 30, 34, 39)
                                      second board: the same four wires, in parallel

 header, seen from above with the USB ports at the bottom:
          3V3 ●1  2● 5V        ← official display power usually on 2 or 4 (5 V) and 6 (GND)
          SDA ●3  4● 5V
          SCL ●5  6● GND
              ●7  8●
          GND ●9 10●
```

The official touchscreen takes its power from the header, normally pins 2 or 4 and 6. Look at
where its two wires sit before plugging in; use pin 9 for the board's ground if 6 is taken.
If the display also has wires on pins 3 and 5 (only very old setups do), the board shares that
bus without trouble: its addresses (0x26, 0x27) differ from the display's.

- Leave the **PUR** pads open on both boards: the Pi already has pull-up resistors on these pins.
- Address pads: board 1 all open = **0x27**. Board 2 with **A0 bridged**, A1 and A2 open = **0x26**.
- The board also has a fused connection to the 12 V battery supply. VanTurtle's installation guide
  shows it in pictures I could not read; follow their guide for that connection and the fuse.
- The Pi and the fans must share the van's negative, which they do when both run from the house battery.

| Board / channel | Cable to |
|---|---|
| 0x27 channel 1 | Fan 1, RJ45 jack |
| 0x27 channel 2 | Fan 2, RJ45 jack |
| 0x26 channel 1 | Fan 1, RJ11 jack |
| 0x26 channel 2 | Fan 2, RJ11 jack |

## Venus OS on the Pi: enable I2C

These steps come from Victron community posts, not official documentation, so check each one.

1. SSH in as root and add `dtparam=i2c_arm=on` on its own line in `/u-boot/config.txt`. Reboot.
2. `ls /dev/i2c-1` should exist. If not, run `modprobe i2c-dev` and look again.
3. `i2cdetect -y 1` should show `27` (and `26` with two boards).
4. `cat /etc/venus/gpio_list` must not list GPIO 2 or 3 (they are the I2C pins).
5. After a Venus OS update, check that the line is still in `/u-boot/config.txt`.

`install.sh` checks steps 2–4 and stops with instructions if something is missing.

## Bench checks with the fans connected

Stop the driver first (`svc -d /service/dbus-maxxfan-bridge`). Fan 1 uses registers `0x02`
(keys) and `0x00` (sense); fan 2 uses `0x03` and `0x01`.

```sh
for b in 0x27 0x26; do i2cset -y 1 $b 0x02 0x00; i2cset -y 1 $b 0x06 0x01; done   # channel 1 ready, nothing pressed
press() { i2cset -y 1 $1 0x02 $(( $2 | 2 )); sleep ${3:-0.15}; i2cset -y 1 $1 0x02 0x00; sleep 0.3; }

press 0x27 0x80          # Beep: the fan should beep
press 0x27 0x10 0.75     # On/Off
press 0x27 0x20          # Faster
press 0x27 0x40          # Slower
press 0x27 0x08          # In/Out
press 0x27 0x60          # Faster+Slower: does the lid open/close on your 7000K/7500K?
press 0x27 0x04          # Auto
i2cget -y 1 0x27 0x00    # bit 0 = 0 means auto is on
press 0x26 0x40          # RJ11 Off: does it also close the lid? (the driver copes either way)
press 0x26 0x20          # RJ11 Open
press 0x26 0x10          # RJ11 Close
```

(Skip the `0x26` lines with only one board; the loop's `0x26` writes will just report an error.)

Write down, and put the answers in `config.ini` for both fans:

| Question | Setting |
|---|---|
| Does RJ11 Off also close the lid? | `rj11_off_closes_lid = yes` or `no` |
| Does switching on with the RJ45 On/Off open the lid by itself? | `on_opens_lid = yes` or `no` |
| How long is a full lid stroke (time an open and a close)? Add 2 s | `lid_settle_s` |
| Does On/Off need the 0.75 s hold, or does 0.15 s work? | `onoff_press_s` |
| Is a single key after a few minutes of quiet sometimes ignored? If never, save a beep per command | `wake_beep = no` |

Until the first two are answered, the driver assumes either key might move the lid and waits
for a full stroke before the next lid-moving key. In the worst case, switching on a fan whose
lid shows open takes about 25 s: Off, wait, On, wait, Open. With the answers filled in, most
commands start straight away.

Start the driver again with `svc -u /service/dbus-maxxfan-bridge`.

## What the driver does

- **At start it presses nothing.** It reads the auto-sense line and restores its last belief from
  `state-<fan>.json`, so a Venus reboot does not disturb running fans.
- A touch on the screen updates the card at once; the presses follow, one at a time, so dragging
  the speed slider does not queue up dozens of steps.
- Before a burst of presses after a quiet spell it sends one **Beep**, because a sleeping fan
  swallows its first key and every count after it would be off by one.
- It never keys the lid while it may still be moving: a lid keyed mid-stroke reverses hard,
  which people with these fans report as noisy. Keys that may move the lid wait for
  `lid_settle_s` after the previous one.
- Touching a manual control while the fan is in auto mode first leaves auto mode.
- Auto mode pressed on the keypad or remote is noticed within 2 seconds and not fought.
- If the I2C bus fails, the cards show disconnected and the driver retries every 10 seconds.

## When the screen and the fan disagree

This only happens after someone uses the ceiling keypad or the handheld remote. The screen can
only send a value different from the one it shows, so a fix is often "away and back".

| Wrong on screen | Fix |
|---|---|
| On/off (two boards) | Tap the toggle: the fan follows whatever the card now shows. Tap again if you wanted the other state |
| Lid (two boards) | Same: Open and Close are absolute, so the fan always follows the card |
| On/off or lid (one board) | Press the matching key on the ceiling keypad once, so the fan matches the card |
| Speed | Slide to 10 % (if the card already shows 10 %, go up a step first), then to the speed you want |
| Direction | Press In/Out on the ceiling keypad once |

## Expect beeps

The fan beeps on every key, as it does with its own keypad. Changing speed from 20 % to 70 %
is five beeps, plus one wake beep. Re-homing at 10 % is about eleven.
