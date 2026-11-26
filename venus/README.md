# Installing on the Pi (Venus OS)

The driver `dbus-maxxfan-bridge` runs on the Raspberry Pi and creates the three switch-pane
cards: Alle fans, Bed and Keuken. It talks to the two VanTurtle Smart Controllers through the
MQTT broker built into Venus OS.

It is installed and kept up to date as a [SetupHelper](https://github.com/kwindrem/SetupHelper)
package called **MaxxFanBridge**. SetupHelper's PackageManager puts it back after every Venus OS
update, installs new versions, and can remove it again.

**First time? Follow [`SETUP.md`](../SETUP.md)**, which goes through everything in order. This
page is the reference for installing, updating, settings and troubleshooting.

| On the Pi | What |
|---|---|
| `/data/MaxxFanBridge` | The package. Replaced as a whole by every update: don't edit anything in here |
| `/data/setupOptions/MaxxFanBridge/config.ini` | **Your settings**: fan names, language, presets, the values from the bench checks. Updates leave this folder alone |
| `/data/setupOptions/MaxxFanBridge/state-fan1.json`, `presets.json` | The lid memory and presets saved with *Opslaan als* (same folder) |
| `/var/log/dbus-maxxfan-bridge/current` | The driver's log |
| `/var/log/PackageManager/current` | SetupHelper's log: installs, updates, errors |

## Prerequisites

1. Venus OS 3.70 or newer, showing the **new UI (gui-v2)** on the touchscreen. The switch pane
   only exists there.
2. Root access: *Settings → General → Access level → Superuser* (hold the right arrow on
   "User & installer" to reveal it), set a root password, enable SSH on LAN.
3. *Settings → Integrations → MQTT Access → on*, the Pi on the van's 2.4 GHz WiFi with a fixed
   address, and a security profile that lets the controllers in: see "Venus OS: let the
   controllers into the broker" in `hardware/vanturtle-smart-controller.md`.
4. For Dutch throughout, set the Venus OS display language to **Nederlands**. The card texts
   come from `config.ini`; gui-v2 draws the rest (Aan/Uit, menus) in the Venus OS language.

## About SetupHelper on gui-v2

SetupHelper's PackageManager menus exist only in the **classic UI**; gui-v2 has none (checked
in SetupHelper v9.7). PackageManager still runs in the background and does its work without
them: it takes packages from a USB stick, installs them, reinstalls them after a Venus OS
update, and downloads updates from GitHub if told to. This guide therefore uses a USB stick
and a few commands over SSH. If your Venus OS version still lets you switch the display to the
classic UI, the menus are at the bottom of *Settings* there.

## 1. Install SetupHelper (once)

Easiest, from its [ReadMe](https://github.com/kwindrem/SetupHelper#blind-install): download
`venus-data-SetupHelperInstall.tgz` (on a Mac, stop Safari from unpacking it), copy it to an
empty USB stick, put the stick in the Pi, reboot, and remove the stick once the screen is back.
Or over SSH, with the Pi on the internet:

```sh
wget -qO - https://github.com/kwindrem/SetupHelper/archive/latest.tar.gz | tar -xzf - -C /data
rm -rf /data/SetupHelper && mv /data/SetupHelper-latest /data/SetupHelper
/data/SetupHelper/setup install
```

## 2. Install MaxxFanBridge

**With a USB stick** (no internet needed). On your computer, in this project folder:

```sh
tools/make-package.sh
```

Copy `.build/MaxxFanBridge-latest.tar.gz` as it is, without unpacking it, to the top folder of
a USB stick, and put the stick in the Pi. Within a minute PackageManager copies it to
`/data/MaxxFanBridge` and installs it. Watch it happen with
`tail -F /var/log/PackageManager/current | tai64nlocal`, then take the stick out.

**Or from GitHub**, from [Born2Ski/MaxxFanBridge](https://github.com/Born2Ski/MaxxFanBridge).
This needs the repository to stay public (see "Updates" below). Over SSH:

```sh
wget -qO - https://github.com/Born2Ski/MaxxFanBridge/archive/latest.tar.gz | tar -xzf - -C /data
rm -rf /data/MaxxFanBridge && mv /data/MaxxFanBridge-latest /data/MaxxFanBridge
/data/MaxxFanBridge/setup install
```

Either way, the install creates `/data/setupOptions/MaxxFanBridge/config.ini` from the
defaults and starts the driver. The cards appear in the switch pane (the toggle icon at the top
of the screen). A fan card shows as disconnected until its controller sends its first live
message; its keepalive comes every 60 s.

## 3. Your settings

Edit `/data/setupOptions/MaxxFanBridge/config.ini` over SSH (`vi`, or `nano` if your Venus OS
has it): fan names, language, the settings from the bench checks, the presets. Then restart
the driver:

```sh
svc -t /service/dbus-maxxfan-bridge
```

To start again from the defaults, delete that `config.ini` and restart: the driver writes a
fresh one.

**Card titles are kept by Venus OS**, not read from `config.ini` each time: the `name =` lines
only set a card's title when the card first appears. To rename a card later, use the switch
pane's edit mode, or over SSH (here the presets card, to `Alle fans`):

```sh
for k in $(sed -n 's/^\[preset \([a-z0-9_]*\)\]/\1/p' /data/setupOptions/MaxxFanBridge/config.ini) save; do
  dbus-send --system --print-reply --dest=com.victronenergy.switch.maxxfan_presets \
    /SwitchableOutput/$k/Settings/Group com.victronenergy.BusItem.SetValue variant:string:"Alle fans"
done
dbus-send --system --print-reply --dest=com.victronenergy.switch.maxxfan_presets \
  /CustomName com.victronenergy.BusItem.SetValue variant:string:"Alle fans"
```

For a fan card, use `com.victronenergy.switch.maxxfan_fan1` (or `fan2`) and the controls
`fan speed direction lid mode`. gui-v2 sorts the cards alphabetically by title.

## Updates

A new version of this project has a higher number in the `version` file at the top of the
project folder. PackageManager installs any version that differs from the installed one.

- **USB stick:** run `tools/make-package.sh` again and put the new archive on the stick, as in
  step 2. Your settings stay.
- **GitHub:** the project lives at
  [github.com/Born2Ski/MaxxFanBridge](https://github.com/Born2Ski/MaxxFanBridge), and its
  `gitHubInfo` file (`Born2Ski:latest`) tells PackageManager where to look. PackageManager
  downloads without logging in, so the repository has to stay **public** for this.
  To release: raise `version`, commit, and move the tag `latest` to that commit:

  ```sh
  git tag -f latest && git push origin main && git push -f origin latest
  ```

  Then tell PackageManager once to look for updates every day:

  ```sh
  dbus -y com.victronenergy.settings /Settings/PackageManager/GitHubAutoDownload SetValue 3
  ```

  (0 = off, 1 = every 10 minutes, 2 = hourly, 3 = daily). New versions are downloaded and,
  because the package carries the `AUTO_INSTALL` flag, installed by themselves.
- **After a Venus OS update** PackageManager reinstalls the package at the next boot; nothing
  to do.

## Try it without the controllers

Only **before** the controllers are set up, and clean up afterwards (last line): a retained value
left on the broker is handed to a controller as a command when it connects. On the Pi, pretend to
be the Keuken fan's controller:

```sh
mosquitto_pub -r -t maxxfan/fan1/vt/speed -m 4       # retained state: shown, still disconnected
mosquitto_pub -t maxxfan/fan1/vt/alive -m 1          # a live message: the card connects
mosquitto_sub -v -t 'maxxfan/fan1/vt/#'              # then touch the controls on the screen
```

Touching Snelheid prints the command (`maxxfan/fan1/vt/speed 7` for 70 %). Confirm it as the
controller would with `mosquitto_pub -r -t maxxfan/fan1/vt/speed -m 7`. Without that, the driver
sends it again after 10 seconds, and 10 seconds later shows 40 % again. The card disconnects
150 seconds after the last `alive`. Clean up with `mosquitto_pub -r -n -t maxxfan/fan1/vt/speed`.

## Troubleshooting

| Symptom | Check |
|---|---|
| Not installed after the USB stick | `tail -50 /var/log/PackageManager/current \| tai64nlocal`. "versions are the same": that version is already there. The archive must keep its name `MaxxFanBridge-latest.tar.gz` and sit in the stick's top folder |
| Install refused: paho-mqtt is missing | This Venus OS version lacks the MQTT library. Copy the pure-Python `paho` package folder (from the `paho-mqtt` wheel on PyPI) into `/data/setupOptions/MaxxFanBridge/`, so you have `/data/setupOptions/MaxxFanBridge/paho/mqtt/client.py`, then run `/data/MaxxFanBridge/setup install`. Updates leave it there |
| No card | `tail /var/log/dbus-maxxfan-bridge/current \| tai64nlocal`; `svstat /service/dbus-maxxfan-bridge`; `dbus -y \| grep maxxfan` should list one service per fan plus `maxxfan_presets` |
| The driver stops at start | The log names the bad line in `config.ini` |
| Card stays disconnected | `mosquitto_sub -v -t 'maxxfan/#'` on the Pi: you should see `maxxfan/fan1/vt/alive 1` every minute. If not, check the controller's broker address, the Pi's fixed address, MQTT access and the security profile |
| Controller cannot connect to the broker | The security profile may only allow encrypted MQTT. Try the profiles in the order the hardware guide gives |
| Card shows a value, then jumps back after about 20 s | The controller did not confirm. Check its topic names against `config.ini`; the log says "did not confirm" |
| Commands sometimes ignored by the controller | Raise `quiet_s` above the controller's Echo suppress; leave its voltage, current and power topics empty |
| Fan does nothing although the card is connected | Run the bench checks (`SETUP.md`, step 12); check the RJ45 lead has all 8 conductors |
| One card keeps going grey and coming back, or the two take turns | `mosquitto_sub -v -t 'maxxfan/+/vt/alive'` should show both fans once a minute. If only one at a time, the controllers are pushing each other off the broker (same login name): ask VanTurtle |
| Keuken card moves the Bed fan | The topics went into the wrong controller: fix them on the controllers' MQTT pages (`fan1` in Keuken's) |
| Richting always the wrong way round, also right after a power cut | `swap_direction = yes` under that fan in `config.ini`, then restart the driver |
| Klep (lid) on the card is the wrong way round | Press Open/Close on the ceiling keypad once (hardware guide, "When the screen and the fan disagree"). After a reinstall or a deleted `state-*.json`, the driver assumes the lid is closed |
| No Alle fans card | The log names the bad `[preset …]` line; each fan line must be `off`, `off open`, `off closed`, `intake N`, `exhaust N` (N = 10…100), `auto` or `keep`. A running fan cannot have `closed`: closing the lid switches it off |
| A preset does something other than `config.ini` says | It was changed with *Opslaan als*: look in `/data/setupOptions/MaxxFanBridge/presets.json`; delete the file to go back to `config.ini` |
| Texts half Dutch, half English | Set the Venus OS display language to Nederlands; `language = nl` under `[gui]` in `config.ini` |
| A slider or dropdown looks wrong | Change that control's type in the switch pane's edit mode, or set `/SwitchableOutput/<key>/Settings/Type` (speed accepts 2 or 7) |

## Remove

```sh
/data/MaxxFanBridge/setup uninstall
```

This stops and removes the driver; PackageManager will not reinstall it by itself. Your
settings stay in `/data/setupOptions/MaxxFanBridge` for a later reinstall; delete that folder
and `/data/MaxxFanBridge` to remove everything.
