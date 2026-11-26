# MaxxFan control from the Venus OS touchscreen

Two MaxxFan Deluxe (7000K / 7500K) roof fans, **Keuken** and **Bed**, controlled from the
switch pane of Venus OS's new UI (gui-v2): a Raspberry Pi 3B with the official 7" touchscreen,
running Venus OS 3.85. The same cards appear in Remote Console and VRM.

**Status: design + first-draft code. Nothing here has met a fan yet.** The driver is tested on
a desktop against stand-ins for D-Bus, MQTT and the VanTurtle controller (`tests/`).

**Setting up for the first time: follow [`SETUP.md`](SETUP.md)**, step by step from the Pi to
both fans, with a check after each part and the bench checks that settle what VanTurtle doesn't
document.

## How it works

```
 Keuken fan ── VanTurtle Smart Controller (inside the fan) ─┐
                                                            │  van WiFi, 2.4 GHz, MQTT
 Bed fan ───── VanTurtle Smart Controller (inside the fan) ─┤
                                                            │
                                    Raspberry Pi, Venus OS ─┴─ MQTT broker (built into Venus OS)
                                                               dbus-maxxfan-bridge ── D-Bus ── gui-v2 switch pane
                                                                                               Remote Console, VRM
```

- A **VanTurtle Smart Controller** sits inside each fan. It presses the fan's keys through the
  fan's wall-control jack, like a wired wall control, and measures the fan's current. With
  VanTurtle's **Advanced WiFi** firmware it joins the van's WiFi and talks MQTT to the broker
  built into Venus OS. Nothing to build, solder or flash.
- **dbus-maxxfan-bridge**, a small program on the Pi, turns that into native switch-pane cards.
  Nothing in gui-v2 is modified, so Venus OS updates do not break it. It is installed, updated
  and reinstalled after Venus OS updates as the [SetupHelper](https://github.com/kwindrem/SetupHelper)
  package **MaxxFanBridge**.
- If the Pi or the WiFi stops, the fans work from their own keypad and remote as before.

## On the screen

Three cards, in Dutch (`[gui] language = nl` in `config.ini`), here just after tapping Koken:

```
┌──── Alle fans ────┐  ┌────────────── Bed ─────────────┐  ┌──────────── Keuken ────────────┐
│ Koken      [ Aan ]│  │ Ventilator              [ Aan ]│  │ Ventilator              [ Aan ]│
│ Slapen     [ Uit ]│  │ Snelheid   ──●────────    30 % │  │ Snelheid   ─────●─────    80 % │
│ Rijden     [ Uit ]│  │ Richting       [ Inblazen  ▾ ] │  │ Richting       [ Afzuigen  ▾ ] │
│ Standaard  [ Uit ]│  │ Klep open               [ Aan ]│  │ Klep open               [ Aan ]│
│ Opslaan als [— ▾] │  │ Modus          [ Handmatig ▾ ] │  │ Modus          [ Handmatig ▾ ] │
└───────────────────┘  └────────────────────────────────┘  └────────────────────────────────┘
```

- **Alle fans** sets both fans with one tap: Koken, Slapen, Rijden, Standaard. *Opslaan als*
  stores the fans as they are into a preset. Contents are in `config.ini`. gui-v2 sorts the
  cards alphabetically by title, which is what puts this card on the left.
- **Klep open** off switches the fan off first; switching it on only opens the lid, the fan
  stays off until you switch it on.
- What a card can trust: Ventilator, Snelheid and Modus are reported by the controller, so they
  follow the ceiling keypad and the remote too. Richting is the controller's guess. Klep (the
  lid) is believed by the driver: if it shows the wrong way, press Open/Close on the ceiling
  keypad once.
- **Plugin card** (Venus OS with gui-v2 1.4.6 or later): one *Alle fans* card with an icon per
  preset, the active one lit (Aangepast when none is), and Bed › / Keuken › rows that open each
  fan's page. It is installed with the package and appears by itself once gui-v2 can load it;
  `cards = plugin` in `config.ini` then hides the switch cards above. See `docs/ui.md`.
- Details: `docs/ui.md`. Interactive design at 800×480: [MaxxFan switch pane](https://claude.ai/artifact/URemBE8xJgGaqg2khCpj6J)
  (local copy in `docs/gui-mockup/`).

## Build order

All steps, in order and with a check after each part, are in [`SETUP.md`](SETUP.md):

1. **The Pi**: fixed address on the van's 2.4 GHz WiFi, MQTT access, SetupHelper, this package.
   The cards appear and wait for the controllers.
2. **Keuken**: fit the controller, put it on the WiFi, calibrate, type in its topics, run the
   bench checks, put the answers in `config.ini`.
3. **Bed**: the same with `fan2`.
4. **Both together**, then the presets.

## What is where

| Path | What |
|---|---|
| `SETUP.md` | **First-time setup, step by step**, including the bench checks and what to expect on first use |
| `hardware/vanturtle-smart-controller.md` | Background: what the controller senses, what you need, wiring in the fan, network and Venus OS security, limits |
| `venus/README.md` | Installing and updating with SetupHelper, your settings, trying it without hardware, troubleshooting |
| `venus/dbus-maxxfan-bridge/` | The driver, and `config.default.ini`: the settings a fresh install starts from (fan names, language, presets). On the Pi you edit `/data/setupOptions/MaxxFanBridge/config.ini` |
| `setup`, `version`, `firstCompatibleVersion`, `AUTO_INSTALL`, `services/` | What makes this folder a SetupHelper package. Raise `version` for every release |
| `tools/make-package.sh` | Builds the package archive for a USB stick |
| `gui-plugin/` | The plugin card for gui-v2 1.4.6 and later: QML and icons in `MaxxFanBridge/`, compiled into `MaxxFanBridge.json` by `tools/make-plugin.sh` |
| `docs/ui.md` | The cards and how they behave |
| `docs/gui-mockup/` | Local copy of the screen design |
| `tests/` | Desktop tests of the driver |
| `archive/` | Other ways to connect the fans that were worked out but not chosen. Not needed for this setup |

## Things I could not verify from here

| Assumption | Source | Risk if wrong |
|---|---|---|
| Smart Controller MQTT: one topic per field both ways, QoS 1, full state on connect, keepalive every 60 s, speed 1–10, lid "any value triggers" | VanTurtle WiFi firmware documentation (retained is implied, not stated) | Adjust `vtwifi.py`; the bench checks show it in minutes |
| Echo suppress ignores *all* incoming messages for its window, not just echoes | Inferred from VanTurtle's description | If it only ignores echoes, the driver is just a little slower than needed |
| Whether MQTT direction is absolute or a toggle | Not documented (REST and web app toggle) | Driver works either way; never repeats it |
| Which way MQTT direction 0 and 1 are | VanTurtle: "0 = maybe forward, 1 = maybe reverse"; the driver reads 0 as intake | Richting shown the wrong way round: `swap_direction = yes` (bench check 12d) |
| Whether MQTT Auto temp is absolute or a toggle | Not documented; the web app's button toggles | Driver works either way; never repeats it |
| Two controllers can be connected to one broker at the same time (different MQTT client names) | Not documented | They push each other off; cards flicker. Check 4 in `SETUP.md` shows it; only VanTurtle can fix it |
| Hotspot password of a new controller | VanTurtle: "something like 0000-0000" | Ask VanTurtle |
| The controller senses on/off and speed (from current), not just believes them | VanTurtle's installation guide: calibration lets it "detect changes made through the fan's original button panel or IR remote" | On/off and speed would drift like the lid after keypad use |
| Manual keys do nothing while the fan is in Auto | Assumption | Driver leaves Auto first anyway |
| WiFi firmware offers MQTT username/password and port fields | Not documented: the only field mentioned is the broker address | Without them, the Venus OS security profile must be Unsecured |
| Which security profile opens plain MQTT on 1883 in Venus OS 3.85 | Victron forum posts disagree between versions | Try the order given in the hardware guide |
| Venus OS's broker accepts other topics (`maxxfan/...`) | Read in the dbus-flashmq source | — |
| The controller's lid open/close works on the 7000K/7500K | VanTurtle offers it; it presses Faster+Slower, which only "some models" accept | Lid not controllable from the screen; the bench check shows it |
| Whether Off closes the lid, whether On opens it, lid stroke time | Sources disagree; not measured | Driver plays safe; set the options after the bench check |
| Auto on starts the fan and opens the lid | VanTurtle (first half); assumption (second) | Lid belief wrong after Auto |
| gui-v2 renders the slider and dropdowns as expected | Venus OS D-Bus wiki; behaviour changed between betas | Change `Type` per control |
| gui-v2 shows our Dutch names as given and draws Aan/Uit and menus in the Venus OS language | gui-v2 behaviour | Some texts in English until the Venus OS language is Nederlands |
| SetupHelper's PackageManager installs from a USB stick, honours `AUTO_INSTALL` and reinstalls after Venus OS updates without its menus (classic UI only) | Read in SetupHelper v9.7's source | Run `/data/MaxxFanBridge/setup install` over SSH |
| Venus OS 3.85 still includes python3 paho-mqtt | Not checked | The install says so; copy paho into the settings folder (`venus/README.md`) |
| Venus OS 3.85 includes `mosquitto_sub` / `mosquitto_pub` | Not checked | Run them from a laptop with `-h <pi-address>` |
| The plugin card loads in the switch pane with gui-v2 1.4.6 or later, and older gui-v2 ignores it | gui-v2 source and plugin guide, v1.4.6; Victron calls the plugin API unfinished | No card, or the API changes; the switch cards keep working with `cards = native` |
| Opening a fan's page from a row on a card in the switch pane works | gui-v2 documents it for lists; the card uses the same list item | The rows do nothing; use the switch cards for the details |
| The plugin card also shows in Remote Console and VRM | gui-v2 1.4.6 loads plugins there over MQTT, if Venus OS publishes them | Only on the touchscreen; keep `cards = native` if you use Remote Console |
| The plugin card looks as on the desktop test's screenshots | Desktop stand-ins for gui-v2's plugin types (`tests/plugin_stubs`) | Spacing or text size differ on the Pi |
| Removing the package can delete the cards' settings from Venus OS (`RemoveSettings` on `/Settings/Devices`) | Read in Victron's localsettings source; not tried on a device | After a reinstall the old card titles come back; rename them as in `venus/README.md` |

## Tests

```sh
python3 tests/test_driver.py        # D-Bus cards, first start with the default config, Dutch texts
python3 tests/test_package.py       # the SetupHelper package and the USB archive
python3 tests/test_vtwifi.py        # Smart Controller backend against a simulated controller
python3 tests/test_presets.py       # presets card: apply, light/darken, Opslaan als
python3 tests/test_plugin.py        # plugin card on a desktop (PySide6), checked against gui-v2's plugin API
python3 tests/mutation_check.py     # proves the tests catch deliberate mistakes
```

`test_vanturtle.py` and `test_vtboard.py` test driver backends for the archived hardware.

## Prior art used

- [VanTurtle Smart Controller](https://vanturtle.com/maxxfan-bluetooth-smartphone-controller/), its
  [WiFi firmware](https://vanturtle.com/vtsc-docs/smart-controller-wifi-firmware/) and
  [installation guide](https://vanturtle.com/vtsc-docs/installing-the-smart-controller/).
- [dbus-flashmq](https://github.com/victronenergy/dbus-flashmq): how the Venus OS broker checks logins and topics.
- [Venus OS D-Bus wiki, switch section](https://github.com/victronenergy/venus/wiki/dbus#switch): `SwitchableOutput` API.
- [dbus-maxxfan](https://github.com/mcgyver78/dbus-maxxfan): another Venus MaxxFan driver; switch-pane conventions.
- [gui-v2 UI plugins](https://github.com/victronenergy/gui-v2/wiki/How-to-create-GUIv2-UI-Plugins): for an optional custom page.
