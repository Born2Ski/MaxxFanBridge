# First-time setup, step by step

From two boxed controllers to working Keuken, Bed and Snelkeuze cards on the touchscreen.

The order matters: first the Pi (no fans involved), then the Keuken fan completely, then the Bed
fan, then both together. Every part ends with a **check**. Don't go on until it passes; the
troubleshooting table in [`venus/README.md`](venus/README.md#troubleshooting) covers what can go
wrong. Allow an afternoon.

Nothing in this project has met a real fan yet. Steps that rely on something VanTurtle or Victron
don't document say so, and the bench checks in step 12 exist to settle those points.

## What you need on the day

- Everything in "What you need" in the [hardware guide](hardware/vanturtle-smart-controller.md#what-you-need):
  the two controllers, short RJ45 leads, wire and ferrules.
- A phone or laptop with WiFi, and a laptop that can open an SSH session: on a Mac, the Terminal
  app. *SSH* means typing commands on the Pi from the laptop: `ssh root@<pi-address>`.
- The van's WiFi router switched on, and its admin page login. You need its list of connected
  devices, and you'll reserve fixed addresses there.
- Internet on the Pi for one install step, or a USB stick instead.

## Worksheet: write these down as you go

| What | Keuken (fan1) | Bed (fan2) |
|---|---|---|
| Van WiFi name (2.4 GHz) | | |
| Pi address (fixed) | | |
| Controller address (fixed) | | |
| Controller hotspot password | | |
| Lid opens by itself when switched on? (step 12a) | yes / no | yes / no |
| Seconds until `speed 7` came back (12b) | | |
| Seconds for a full lid stroke (12c) | | |
| Richting opposite to the air? (12d) | yes / no | yes / no |

Keep the Pi's root password somewhere safe, not on this sheet.

---

## Part 1: the Pi

Menu names below are from Venus OS 3.x and differ a little between versions; look nearby if one
isn't exactly where it says.

### Step 1. Venus OS and the screen

1. Venus OS **3.70 or newer** (this van has 3.85), and the touchscreen showing the **new UI**
   (gui-v2). The switch pane, where the cards appear, only exists there.
2. Set the display language to **Nederlands**. The driver supplies the Dutch card texts; Venus
   OS draws the rest (Aan/Uit, menus) in its own language.

### Step 2. WiFi and a fixed address for the Pi

1. Join the Pi to the van's WiFi. It has to be **2.4 GHz**: the Pi 3B and the controllers can't
   use 5 GHz.
2. In the router's admin page, find the Pi in the connected devices and **reserve its address**
   (often called "DHCP reservation" or "static lease"). Write it down. The controllers are told
   this address once and never look it up again, so it must not change.

### Step 3. Root access and SSH

1. *Settings → General → Access level*: hold the right arrow on "User & installer" until
   **Superuser** appears, and choose it.
2. Set a **root password**, and switch on **SSH on LAN**.
3. Check from the laptop, on the van's WiFi: `ssh root@<pi-address>` asks for that password and
   gives you a prompt. All commands below are typed there.

### Step 4. Let the controllers use the Pi's MQTT broker

1. *Settings → Integrations → MQTT Access → on.*
2. **Network security profile.** VanTurtle's documentation shows only one MQTT field on the
   controller: the broker address. It mentions no port, username or password. If your controller
   really has none, only the profile **Unsecured** lets it in. Choose that profile when you get to
   step 11, unless the controller's MQTT page turns out to have a password field; then see
   "Venus OS: let the controllers into the broker" in the
   [hardware guide](hardware/vanturtle-smart-controller.md#venus-os-let-the-controllers-into-the-broker).
   With Unsecured, anyone on the van's WiFi can use Remote Console and MQTT without a password,
   so give the WiFi a strong WPA2 password.

### Step 5. Install SetupHelper

SetupHelper installs this project, puts it back after every Venus OS update and fetches new
versions. With the Pi on the internet, over SSH:

```sh
wget -qO - https://github.com/kwindrem/SetupHelper/archive/latest.tar.gz | tar -xzf - -C /data
rm -rf /data/SetupHelper && mv /data/SetupHelper-latest /data/SetupHelper
/data/SetupHelper/setup install
```

(No internet on the Pi: see "Install SetupHelper" in [`venus/README.md`](venus/README.md#1-install-setuphelper-once)
for the USB-stick way.)

### Step 6. Install MaxxFanBridge and switch on automatic updates

```sh
wget -qO - https://github.com/Born2Ski/MaxxFanBridge/archive/latest.tar.gz | tar -xzf - -C /data
rm -rf /data/MaxxFanBridge && mv /data/MaxxFanBridge-latest /data/MaxxFanBridge
/data/MaxxFanBridge/setup install
dbus -y com.victronenergy.settings /Settings/PackageManager/GitHubAutoDownload SetValue 3
```

The last line makes the Pi look for a new version once a day, whenever it has internet.

### ✅ Check 1: the cards are there

- Tap the switch icon in the top bar of the touchscreen. Three cards: **Keuken** and **Bed**
  (greyed out: no controllers yet, that's expected) and **Snelkeuze**.
- If not: `svstat /service/dbus-maxxfan-bridge` should say `up`, and
  `tail /var/log/dbus-maxxfan-bridge/current | tai64nlocal` says what is wrong. An install
  refused for "paho-mqtt is missing" has its own row in the troubleshooting table.

---

## Part 2: the Keuken controller (fan1)

Do Keuken completely, from wiring to check 3, with the **Bed fan's fuse pulled**. Both controllers
create the same hotspot and use the same network name (`vanturtle-fan`), so doing one at a time
is how you tell them apart.

### Step 7. Fit the controller in the fan

Follow "Wiring at each fan" in the
[hardware guide](hardware/vanturtle-smart-controller.md#wiring-at-each-fan). The points that
matter most:

- Pull the fan's fuse first.
- Use the supply wires to the fan's control board, **not the motor wires**, which are also
  black and white.
- Plug the RJ45 lead into the fan's wall-control jack **before** lowering the fan back into the
  roof opening.
- Refit the fuse: a short beep and a lit LED mean the controller has power.

### Step 8. Put the controller on the van's WiFi

1. With the phone or laptop, join the WiFi network **VanTurtle Fan**. VanTurtle's documentation
   gives the password only as "something like 0000-0000"; look on the controller, its packaging
   or your order email, or ask VanTurtle. Write it on the worksheet.
2. A setup page usually opens by itself. If not, open **http://192.168.4.1**: type the `http://`,
   because the page doesn't work over `https`.
3. Tap the **cog** (top right) → **WiFi settings**, enter the van's WiFi name and password, and
   save.
4. The controller restarts and joins the van's WiFi, and the VanTurtle Fan network disappears.
   If it comes back after a minute or so, the controller could not connect: check the password
   and that the network is 2.4 GHz, and try again.

### Step 9. Give the controller a fixed address

1. In the router's list of connected devices, find the new device (probably named
   `vanturtle-fan`), **reserve its address** and write it down.
2. On the laptop, open `http://<controller-address>`. You get VanTurtle's page with a speed
   slider. Don't rely on `vanturtle-fan.local`: with two controllers that name points at
   either one.

### Step 10. Calibrate

**Hold the CALIBRATE button on the controller for 3 seconds** (VanTurtle's app and web page can
start it too). The fan opens its lid and runs through its speeds, for about a minute. **Don't
touch the ceiling keypad or the remote** meanwhile. The controller learns the fan's current at
each speed, which is how it notices keypad and remote presses later.

### Step 11. MQTT settings

On the controller's page: **cog → MQTT section**. Type these in exactly; a control whose topic
has a typo just does nothing.

| Field | Keuken (fan1) |
|---|---|
| Broker address | the Pi's address from the worksheet |
| Port, username, password, if the page has them | 1883; see step 4 |
| On/off | `maxxfan/fan1/vt/on` |
| Speed | `maxxfan/fan1/vt/speed` |
| Direction | `maxxfan/fan1/vt/dir` |
| Auto temp | `maxxfan/fan1/vt/auto` |
| Open/close | `maxxfan/fan1/vt/lid` |
| Keepalive | `maxxfan/fan1/vt/alive` |
| Voltage, Current, Power | **leave empty** |
| Echo suppress | `500` |

Save: the controller connects straight away. Now set the security profile on the Pi as decided in
step 4.

Why leave voltage, current and power empty: after each of its own messages the controller ignores
whatever it receives for the *Echo suppress* time. The driver therefore only sends when the
controller has been quiet for 2 seconds. If the controller published power every second or two,
it would never be quiet.

### ✅ Check 2: the Keuken card comes alive

- Within a minute the **Keuken** card is no longer greyed out. (The controller sends a "still
  here" message every 60 seconds.)
- Over SSH, `mosquitto_sub -v -t 'maxxfan/fan1/#'` shows the controller's values and
  `maxxfan/fan1/vt/alive 1` once a minute. Stop it with Ctrl-C.
- Still grey after two minutes: work through "Card stays disconnected" in the troubleshooting table.

`mosquitto_sub` and `mosquitto_pub` should be on the Pi; I haven't checked that Venus OS 3.85
still has them. If they're missing, run the same commands on the laptop with `-h <pi-address>`
added (on a Mac: `brew install mosquitto`).

### Step 12. Bench checks (about 15 minutes)

These answer what VanTurtle doesn't document, for this fan. Stop the driver so it stays out of
the way, and watch everything the controller says:

```sh
svc -d /service/dbus-maxxfan-bridge
mosquitto_sub -v -t 'maxxfan/#'
```

Open a second SSH window for the commands below. Start with the **fan off and the lid closed**
(use the ceiling keypad), and write the answers on the worksheet.

**a. Does switching on open the lid?**
```sh
mosquitto_pub -t maxxfan/fan1/vt/on -m 1
```
The fan starts and `maxxfan/fan1/vt/on 1` comes back. Did the lid open by itself?

**b. How quickly is speed confirmed?**
```sh
mosquitto_pub -t maxxfan/fan1/vt/speed -m 7
```
Count the seconds until `maxxfan/fan1/vt/speed 7` comes back.

**c. How long does the lid take?** Switch the fan off, then close or open the lid, and time a
full stroke:
```sh
mosquitto_pub -t maxxfan/fan1/vt/on -m 0
mosquitto_pub -t maxxfan/fan1/vt/lid -m 1
```
VanTurtle says Open/close works "even if off". Each message moves the lid the other way.

**d. Which way is Richting?** The lid must be open: if c left it closed, send the `lid` line
once more. Then switch on at a moderate speed:
```sh
mosquitto_pub -t maxxfan/fan1/vt/on -m 1
mosquitto_pub -t maxxfan/fan1/vt/speed -m 5
```
Hold a tissue under the fan. Air blowing down into the van is **Inblazen** (intake); air pulled up
and out is **Afzuigen** (exhaust). Now look at the last `maxxfan/fan1/vt/dir` line: the card
reads `0` as Inblazen and `1` as Afzuigen. VanTurtle only says "0 = maybe forward, 1 = maybe
reverse". If the number says the opposite of the tissue, write **yes** under "Richting opposite".
Then change direction once:
```sh
mosquitto_pub -t maxxfan/fan1/vt/dir -m 1
```
The airflow should reverse, and the `dir` value should change with it.

(The controller can't feel the direction; it counts its own presses. So do this check soon
after power-up, before anyone has pressed In/Out on the keypad or the remote.)

**e. Auto and off.**
```sh
mosquitto_pub -t maxxfan/fan1/vt/auto -m 1    # auto 1 comes back; the fan runs on its thermostat
mosquitto_pub -t maxxfan/fan1/vt/auto -m 0    # auto 0 comes back
mosquitto_pub -t maxxfan/fan1/vt/on -m 0      # fan stops
```

**f. Restart test: nothing may move.** Close the lid with the keypad. Pull the fan's fuse, wait
10 seconds, refit it. The controller reconnects and publishes its values again. **The fan must
not start, the direction must not change and the lid must not move.** If something moves, set
*Echo suppress* to `1500` on the controller's MQTT page and repeat.

**g. Keypad and remote.** Press On/Off and the speed keys on the ceiling keypad and the remote:
`on`, `speed` and `auto` should follow in the first window. Direction and the lid won't: the
controller can't sense them, and that's expected.

Stop `mosquitto_sub` with Ctrl-C.

### Step 13. Put the results in the settings

1. Open the settings: `nano /data/setupOptions/MaxxFanBridge/config.ini` (or `vi` if nano is
   missing).
2. Under `[fan1]`, below `backend = vanturtle-wifi`, add your answers. For example:

   ```ini
   on_opens_lid = no          ; 12a: yes if the lid opened by itself
   lid_settle_s = 14          ; 12c: the stroke time plus 2
   swap_direction = no        ; 12d: yes if Richting was opposite
   ```

   Only if 12b took more than 8 seconds, add `confirm_s =` with that time plus 3.
3. Save and leave the editor (in nano: Ctrl-O, Enter, Ctrl-X).
4. **Fan off and lid closed** (ceiling keypad), then start the driver fresh:

   ```sh
   rm -f /data/setupOptions/MaxxFanBridge/state-fan1.json
   svc -u /service/dbus-maxxfan-bridge
   ```

   Nothing reports the lid's position, so the driver keeps track of it itself. Deleting that
   file makes it start from "closed", which is now true.

### ✅ Check 3: the Keuken card runs the Keuken fan

On the touchscreen, Keuken card:

1. **Klep open → Aan**: the lid opens, the fan stays off.
2. **Ventilator → Aan**, **Snelheid** to 70 %: the fan runs at 70 %. Each touch shows at once,
   and the fan follows within a few seconds.
3. **Richting**: pick the other one; the airflow reverses.
4. **Modus → Automatisch**, then back to **Handmatig**.
5. **Klep open → Uit**: the fan switches off first, then the lid closes.

A value that jumps back after about 20 seconds was not confirmed by the controller: look at
"Card shows a value, then jumps back" in the troubleshooting table.

---

## Part 3: the Bed controller (fan2)

Refit the Bed fan's fuse. The Keuken controller can stay on: it is on the van's WiFi now and no
longer makes a VanTurtle Fan hotspot, so the hotspot you see now is the Bed controller's.

Repeat **steps 7 to 13** with **`fan2` everywhere instead of `fan1`**:

- Step 9: the router now lists two `vanturtle-fan` devices; the new one is the one without a
  reservation yet.
- Step 11: the topics are `maxxfan/fan2/vt/on`, `maxxfan/fan2/vt/speed`, `maxxfan/fan2/vt/dir`,
  `maxxfan/fan2/vt/auto`, `maxxfan/fan2/vt/lid` and `maxxfan/fan2/vt/alive`; the rest is the same.
- Step 12: the bench checks use `maxxfan/fan2/vt/...` (the lid timing and direction can differ
  between the two fans, so don't copy Keuken's answers).
- Step 13: the answers go under `[fan2]`, and the file to delete is `state-fan2.json`.

Then check 3 on the **Bed** card.

### ✅ Check 4: both controllers together

1. Over SSH, for three minutes:

   ```sh
   mosquitto_sub -v -t 'maxxfan/+/vt/alive'
   ```

   Both `maxxfan/fan1/vt/alive 1` and `maxxfan/fan2/vt/alive 1` should appear about once a
   minute each, and both cards stay lit.

   If one card keeps going grey and coming back, or the messages come from only one controller at
   a time, the two controllers are probably pushing each other off the broker. That happens when
   both log in under the same name, and VanTurtle doesn't say whether they do. Nothing on the Pi
   can fix that: ask VanTurtle.
2. The Keuken card must move the **Keuken** fan and the Bed card the **Bed** fan. If they're
   swapped, the topics went into the wrong controller: correct them on the controllers' MQTT
   pages.
3. **Snelkeuze → Koken**: Keuken blows out at 80 %, Bed blows in at 30 %, both lids open. Then
   **Rijden**: both fans stop and both lids close.

That's it: the setup is done.

---

## Part 4: first use, what to expect

- **Open the cards** with the switch icon at the top of the touchscreen. The same cards appear in
  Remote Console and VRM.
- **A touch** shows on the card at once. The fan follows within a few seconds: commands go out one
  at a time, and only when the controller is quiet. Several touches in a row simply take a little
  longer.
- **Klep open Uit** switches the fan off first, then closes the lid. **Klep open Aan** only opens
  it; switch the fan on yourself.
- **Touching anything while the fan is in Automatisch** switches it to Handmatig first.
- **Ceiling keypad and remote** keep working. Ventilator, Snelheid and Modus on the card follow
  them. Richting and Klep don't, because the controller can't sense them. When one of those two is
  wrong on the card, press **In/Out** or **Open/Close** on the ceiling keypad once, so the fan
  matches the card again. Tapping the card doesn't help, because it sends a toggle. If Richting is
  wrong *every time* after a power cut, flip `swap_direction` for that fan in `config.ini` (step 13).
- **A greyed-out card** means no contact with that controller for 2½ minutes: WiFi down, or the
  fan without power. The fan works from its keypad and remote meanwhile, and the card comes back
  by itself.
- **Snelkeuze**: one tap sets both fans, and the lit preset shows what is active. It goes dark when
  someone changes a fan afterwards. **Opslaan als** stores what the fan cards show now into a
  preset.
- **Names, order, hiding a control**: the switch pane's edit mode. Preset contents: *Opslaan als*,
  or the `[preset …]` sections in `config.ini`. More in [`docs/ui.md`](docs/ui.md).

## Part 5: afterwards

- **Updates** arrive by themselves within a day of a new release, whenever the Pi has internet.
  After a Venus OS update, SetupHelper puts the package back at the next start. Your settings are
  kept through both.
- **Keep a copy of your settings** on the laptop:
  `scp root@<pi-address>:/data/setupOptions/MaxxFanBridge/config.ini .`
- **After changing `config.ini`**: `svc -t /service/dbus-maxxfan-bridge` restarts the driver.
- **New WiFi name or password in the van**: the controllers can't connect any more and bring
  back their VanTurtle Fan hotspot; do step 8 again for each, one at a time. If the Pi's address
  changes, change the broker address on both controllers (step 11).
- **Something wrong**: the troubleshooting table in [`venus/README.md`](venus/README.md#troubleshooting).
