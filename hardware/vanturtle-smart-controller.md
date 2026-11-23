# VanTurtle Smart Controller over WiFi (no cables through the van)

One [VanTurtle Smart Controller](https://vanturtle.com/maxxfan-bluetooth-smartphone-controller/)
sits inside each fan. It presses the fan's keys through the RJ45 wall-control jack, like a
wired wall control, and measures the fan's current. With VanTurtle's **Advanced WiFi**
firmware it joins the van's WiFi and talks MQTT to the broker built into Venus OS. The driver
on the Pi turns that into the switch-pane cards Keuken and Bed.

```
 Keuken ── short RJ45 lead ── Smart Controller (inside the fan) ─┐
           fan's 12 V runs through its terminals                 │
                                                                 │  WiFi, 2.4 GHz
 Bed ───── short RJ45 lead ── Smart Controller (inside the fan) ─┤
                                                                 │
                                               van WiFi router ──┴── Raspberry Pi, Venus OS
                                                                     MQTT broker (FlashMQ, port 1883)
                                                                     dbus-maxxfan-bridge ── gui-v2 cards
```

Nothing runs from the fans to the Pi. Each fan keeps working from its keypad and remote if
the Pi, the router or a controller dies.

## What the screen knows

The controller senses some things and believes others. The driver shows what the controller
reports, except for the lid, which nothing reports.

| Control | Source | Notes |
|---|---|---|
| Fan on/off | **Reported**, sensed by the controller | Probably from the motor current; VanTurtle does not say outright |
| Speed | **Reported**, 1–10 shown as 10–100 % | Probably from current after the calibration run |
| Direction | Reported, but VanTurtle calls it "a guess" | The controller toggles In/Out and keeps count |
| Mode (Manual/Auto) | **Reported**, sensed from the fan's auto line | |
| Lid | **Believed by the driver** | One toggle command, no position report |
| Auto setpoint | Not offered | Keys can only nudge it |

After a touch, the card shows the new value while the controller works. Commands go out one
at a time. If the controller has not confirmed one after 10 seconds, the driver sends it once
more (on/off, speed and mode only; direction and lid are toggles and are never repeated). If
there is still no confirmation, the card goes back to what the controller last reported. The
driver never repeats a command after the fan has reported, so it does not fight the keypad or
the remote.

## What you need

| Qty | Item | Notes |
|---|---|---|
| 2 | VanTurtle Smart Controller, **Maxxair Deluxe** (RJ45), firmware **Advanced WiFi** | €19.99 + €4.99 each, plus shipping |
| 2 | Network cable with **short-body RJ45 plug**, all 8 conductors (PoE rated is safe), as short as reaches | Ask VanTurtle whether one comes with the controller |
| | Wire rated at least 5 A, bootlace ferrules | For the controller's screw terminals |
| | 2.4 GHz WiFi router that is always on, if the van has none | The Pi 3B and the controllers use 2.4 GHz only |

Check that the order confirmation says firmware **Advanced WiFi**: the MQTT settings below
are part of that firmware. If it says Bluetooth, ask VanTurtle whether they can change it. If
the order has not shipped yet, also ask them three things:

1. **Leave the flash unlocked** so you could load ESPHome or other firmware later. Otherwise
   the chip is locked for good. It costs nothing and keeps that route open.
2. Does the WiFi firmware's MQTT page have a **port, username and password**? This decides
   the Venus OS security setting below.
3. Is the RJ45 lead included, and does the board come with mounting holes or a holder for the
   fan's corner?

## Wiring at each fan

From VanTurtle's [installation guide](https://vanturtle.com/vtsc-docs/installing-the-smart-controller/).
The controller sits in a spare corner inside the fan, between the existing supply wires and
the fan's control board.

```
 Controller terminals, left to right:

   FAN+      GND       GND        BATT
    │         │         │          │
    │         │         │          └── + from the fuse panel (the fan's existing fused feed)
    │         │         └───────────── − from the van's supply
    │         └─────────────────────── fan − (white) to the fan's control board
    └───────────────────────────────── fan + (black) to the fan's control board

 RJ45 lead: controller ──── fan's RJ45 wall-control jack
```

1. **Pull the fan's fuse** first.
2. Find the two supply wires that feed the fan's green control board. **Do not touch the
   motor wires**: they are also black and white. Some installs use blue and black for the
   supply.
3. Connect the four terminals as shown, with ferrules on stranded wire.
4. Plug the RJ45 lead into the fan's wall-control jack **before lowering the fan into the roof
   opening**. A normal-length plug can snap the jack off when the fan goes back down.
5. Fix the controller in its corner with screws or a cable-tie mount. Sticky pads and Velcro
   may not survive rough roads.
6. Refit the fuse. A short beep and a lit LED mean it has power.

## The network

- The Pi and both controllers join the **same 2.4 GHz WiFi**. A van router is the simple
  choice. A Cerbo GX can be its own access point (at `172.24.24.1`); I have not checked
  whether Venus OS offers that on a Raspberry Pi.
- Give the Pi a **fixed address**: a DHCP reservation in the router, or a manual IP in Venus
  OS's network settings. The controllers are told the broker's address once and do not look
  it up again.
- Use WPA2 with a strong password. VanTurtle documents no login on the controller's web page,
  and depending on the next section, MQTT may have none either. Anyone on this WiFi can run
  the fans.

## Venus OS: let the controllers into the broker

1. *Settings → Integrations → MQTT Access → on.* (The driver itself connects from the Pi and
   needs no password.)
2. The **network security profile** decides whether a device on the WiFi may use plain MQTT
   on port 1883, and with which password. Victron's forum reports differ by version, so try in
   this order and stop at the first that works (the card comes online):
   1. Keep your current profile. If the controller's MQTT page has a password field, enter
      the security profile password (the one Remote Console asks for); the username can be
      anything.
   2. Profile **Weak**, with that same password.
   3. Profile **Unsecured**, no password. Remote Console, MQTT and Modbus-TCP then need no
      password on the van's network; acceptable only on a private, WPA2-protected WiFi.

   From a laptop on the same WiFi, `nc -vz <pi-address> 1883` shows whether the port is open
   at all.

## Setting up each controller

Do one controller at a time, with the other fan's fuse pulled, so you know which is which.
Both answer to the same name (`vanturtle-fan.local`), so use their IP addresses.

1. Join the WiFi network **VanTurtle Fan** with a phone or laptop and open `192.168.4.1`.
2. Enter the van's WiFi name and password. The controller restarts and joins it. If it cannot,
   it brings its own network back so you can try again.
3. Find its new address in the router's list of connected devices and open it in a browser.
4. Run **calibration** from the web page, if it offers it. The fan opens the lid and runs
   through its speeds for about a minute. Don't touch the keypad or remote meanwhile.
5. MQTT settings:

| Controller field | Keuken (fan1) | Bed (fan2) |
|---|---|---|
| Broker address | the Pi's fixed address | same |
| Port / username / password, if offered | 1883 / any / see above | same |
| On/off | `maxxfan/fan1/vt/on` | `maxxfan/fan2/vt/on` |
| Speed | `maxxfan/fan1/vt/speed` | `maxxfan/fan2/vt/speed` |
| Direction | `maxxfan/fan1/vt/dir` | `maxxfan/fan2/vt/dir` |
| Auto temp | `maxxfan/fan1/vt/auto` | `maxxfan/fan2/vt/auto` |
| Open/close | `maxxfan/fan1/vt/lid` | `maxxfan/fan2/vt/lid` |
| Keepalive | `maxxfan/fan1/vt/alive` | `maxxfan/fan2/vt/alive` |
| Voltage, current, power | leave empty for now | leave empty |
| Echo suppress | `500` | `500` |

The prefix (`maxxfan/fan1/vt`) must match `topic =` for that fan in `config.ini`; that is the
default, so normally nothing needs changing there.

Why leave voltage, current and power empty: the controller ignores incoming commands for the
echo-suppress window after each of its own publishes. The driver therefore sends one command
at a time, and only after the controller has been quiet for 2 seconds (`quiet_s`). If the
controller published power every second or two, it would never be quiet. Add them later if
the bench check below shows commands still arrive promptly; the driver ignores them for now.
If you raise *Echo suppress* above 1500, raise `quiet_s` in `config.ini` above it too.

## Bench checks

On the Pi, stop the driver (`svc -d /service/dbus-maxxfan-bridge`) and watch the topics:

```sh
mosquitto_sub -v -t 'maxxfan/#'
```

1. Within a minute you should see `maxxfan/fan1/vt/alive 1`. Right after the controller
   connects, it publishes its full state (`on`, `speed`, `dir`, `auto`).
2. In a second shell, send commands and watch the fan and the topics:

```sh
mosquitto_pub -t maxxfan/fan1/vt/on -m 1       # fan starts; on → 1 comes back
mosquitto_pub -t maxxfan/fan1/vt/speed -m 7    # speed → 7 comes back; note how long it takes
mosquitto_pub -t maxxfan/fan1/vt/dir -m 1      # direction changes?
mosquitto_pub -t maxxfan/fan1/vt/dir -m 1      # again: does it flip back (toggle) or stay?
mosquitto_pub -t maxxfan/fan1/vt/lid -m 1      # lid opens or closes; time a full stroke
mosquitto_pub -t maxxfan/fan1/vt/auto -m 1     # auto → 1 comes back
mosquitto_pub -t maxxfan/fan1/vt/auto -m 0
mosquitto_pub -t maxxfan/fan1/vt/on -m 0
```

3. **Restart test.** Pull and refit the fan's fuse. The controller reconnects and receives its
   own retained values back. **Nothing should move.** If the direction flips or the lid moves,
   raise *Echo suppress* (try 1500) and repeat.
4. Press keys on the ceiling keypad and the handheld remote. Note which topics follow. That is
   what the card will catch from other sources.

Write down, and put the answers in `/data/setupOptions/MaxxFanBridge/config.ini` on the Pi,
under both fans:

| Question | Setting |
|---|---|
| Does switching on (step 2, first line) open a closed lid by itself? | `on_opens_lid = yes` or `no` |
| How long is a full lid stroke? Add 2 s | `lid_settle_s` |
| How long did speed 1 → 7 take before `speed 7` came back? If more than 8 s, set this to that time plus 3 s | `confirm_s` (default 10) |

Start the driver again with `svc -u /service/dbus-maxxfan-bridge`.

## When the screen and the fan disagree

| Wrong on screen | Fix |
|---|---|
| On/off, speed, mode | Should correct itself within seconds: these are reported. If not, check the topics with `mosquitto_sub` |
| Direction | Change it on the card twice, or press In/Out on the ceiling keypad once |
| Lid | Press Open/Close on the ceiling keypad or remote once, so the fan matches the card. Tapping the card does not help: it sends a toggle and the card flips with it |

The lid goes wrong only after someone uses the keypad or remote for the lid, after Auto mode
has run the fan, after calibration (which leaves the lid open), or when a lid command is lost
on the WiFi. That last one cannot be detected: the lid toggle is never confirmed.

## Limits

- **The lid position is believed, not known.** This is the main weakness of this setup. A
  VanTurtle DIY board on the fan's RJ11 jack could open and close it absolutely
  (`archive/README.md`), if it ever matters enough.
- Needs WiFi that is always on. When it drops, the cards show disconnected after about two and
  a half minutes (no keepalive), and the fans keep working from the keypad and remote.
- VanTurtle's firmware is closed. Its MQTT behaviour comes from their documentation, not from
  testing.
- The fan beeps on every key press, as it does with its own keypad.
