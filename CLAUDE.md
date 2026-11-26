# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Control of two MaxxFan Deluxe roof fans, Keuken (`fan1`) and Bed (`fan2`), from the gui-v2 switch
pane of Venus OS (a Raspberry Pi 3B with the 7" touchscreen, Venus OS 3.85; also runs on a Cerbo
GX). One driver process on the Venus device publishes D-Bus switch services; gui-v2, Remote Console
and VRM render them as cards, in Dutch (`[gui] language = nl`).

**The final design (option W, bought):** `backend = vanturtle-wifi`, a VanTurtle Smart Controller
inside each fan with VanTurtle's closed Advanced WiFi firmware, MQTT to the Venus OS broker.
Owner docs: `SETUP.md` (first-time setup step by step, with the bench checks), `README.md`,
`hardware/vanturtle-smart-controller.md` (background), `venus/README.md` (install/update reference,
troubleshooting), `docs/ui.md`.

**Keep the owner docs about the final design only.** Everything for hardware that was worked out
but not chosen lives in `archive/` (docs, ESPHome firmware, C++ tests; `archive/README.md` has the
comparison). The driver still contains those backends, with tests, chosen per fan in `config.ini`:
`vanturtle-esp32` (E: DIY board + ESP32 relay at the fan), `vanturtle` (V: DIY board on the Pi's
I2C pins), `mqtt` (A/C: own ESPHome firmware).

**Nothing has run on real hardware yet.** Unverified assumptions are tracked in the README table
"Things I could not verify from here"; the bench checks for option W are step 12 of `SETUP.md`
(archived hardware docs end in their own). When code relies
on a new assumption about the fans, VanTurtle firmware or Venus OS, add a row there.

## Commands

No build step, no pytest, no linter config. Each test file is a plain script:

```sh
python3 tests/test_driver.py        # Fan service, mqtt backend, I2C wiring, main() on the shipped config, Dutch texts
python3 tests/test_vtwifi.py        # option W backend against a simulated VanTurtle controller
python3 tests/test_presets.py       # presets card
python3 tests/test_package.py       # SetupHelper package layout, builds and checks the USB archive
python3 tests/test_vanturtle.py     # archived option V backend against a simulated fan (all start/target states)
python3 tests/test_vtboard.py       # archived option E: VanTurtle logic through a simulated ESP32 over a lossy link
python3 tests/mutation_check.py     # plants bugs; every mutant must be caught, the unbroken code must pass
mkdir -p .build && c++ -std=c++17 -o .build/test_packet archive/tests/test_packet.cpp && .build/test_packet
mkdir -p .build && c++ -std=c++17 -o .build/test_relay archive/tests/test_relay.cpp && .build/test_relay
```

Run one test function: `python3 -c "import sys; sys.path[:0]=['tests','venus/dbus-maxxfan-bridge']; import test_vtwifi as t; t.test_lid_belief_settle_and_persistence()"`.

Archived ESPHome firmware compiles with the venv in `.build/venv`:
`cd archive/firmware && ../../.build/venv/bin/esphome compile option-a.yaml` (needs `secrets.yaml`,
gitignored; template in `secrets.yaml.example`). Option E per fan: `-s node_id fan2`.

**The project root is a SetupHelper package named `MaxxFanBridge`** (kwindrem/SetupHelper v9.x;
`tests/test_package.py` encodes its rules): `setup` (sources IncludeHelpers, ends in
`endScript INSTALL_SERVICES` — not the guidelines' `INSTALL_SERVICE`), `version` (raise it for every
release: PackageManager only installs a differing version), `firstCompatibleVersion`, `AUTO_INSTALL`
(PackageManager's menus exist only in the classic UI, so installs must happen without them),
`services/dbus-maxxfan-bridge/` (run file starts the driver from `/data/MaxxFanBridge/...`). Package
names may not contain `-`. Updates replace `/data/MaxxFanBridge` wholesale, so everything the user
changes lives in `--data-dir /data/setupOptions/MaxxFanBridge` (config.ini copied from
`config.default.ini` on first start, state-*.json, presets.json, an optional paho copy).
A real uninstall (`UNINSTALL` and not `$installFailed`: SetupHelper also sets UNINSTALL to roll
back a failed install) runs `forget.py`: removes `/Settings/Devices/maxxfan_*` from localsettings
and config.ini, presets.json, state files (owner wants a reinstall to start fresh); paho and
SetupHelper's flags stay. Updates never uninstall. `test_package` checks the guard.
`tools/make-package.sh [github-user]` builds `.build/MaxxFanBridge-latest.tar.gz` for a USB stick.
On GitHub as `Born2Ski/MaxxFanBridge`, public (`gitHubInfo` = `Born2Ski:latest`; PackageManager
downloads the tag `latest` unauthenticated, so it must stay public). Release: raise `version`,
commit, `git tag -f latest`, push main and `git push -f origin latest`.
On the Pi: restart with `svc -t /service/dbus-maxxfan-bridge`; logs in `/var/log/dbus-maxxfan-bridge/current`
and `/var/log/PackageManager/current`.

## Driver architecture (`venus/dbus-maxxfan-bridge/`)

Runs on Venus OS's Python: standard library + Victron's `velib_python` (`vedbus`, `settingsdevice`)
+ `paho-mqtt` for MQTT backends only (may be absent on the device; no pip). Don't add dependencies.

- `dbus-maxxfan-bridge.py`: one `com.victronenergy.switch.maxxfan_<id>` service per fan (class `Fan`),
  plus optional `com.victronenergy.switch.maxxfan_presets` (class `Presets`). `switch_service()`
  builds both: `/SwitchableOutput/<key>/…` paths, and GUI edits (names, groups, visibility, types)
  persisted in localsettings. VanTurtle fans expose 5 controls (`VANTURTLE_KEYS`, no setpoint).
- **Everything happens on the GLib main loop.** The paho thread hands messages over with
  `GLib.idle_add` (`Bridge`); the option V/E worker thread posts through `post`; option W has no thread
  and is driven by `Bridge.tick` every second.
- **The backend seam:** `Fan.publish(fan_id, mqtt_key, value)` sends a command. For `mqtt` it is
  `Bridge.publish` (topics in `archive/docs/mqtt-contract.md`); for the VanTurtle backends it is a closure
  calling `worker.command(key, value)`, set in `vanturtle_worker` / `make_vtwifi_fan`. `Bridge` routes
  topic prefixes (`add_prefix`, no overlaps) to anything with `on_message`, `broker_lost`, `tick`:
  `VtWifiFan` and option E's `BoardLink`.
  Backends show values through `fan.on_state(mqtt_key, str_value)` and `fan.set_online(bool)`.
- Three key vocabularies, easy to mix up: D-Bus control keys `fan speed direction lid mode setpoint`;
  driver/MQTT keys `on speed dir lid mode setpoint` (`OUTPUTS` maps them); option W topic leaves
  `on speed dir auto lid alive` under `maxxfan/<id>/vt/`. Speed is 10–100 % everywhere except on the
  VanTurtle controller (1–10).
- `vanturtle.py` (options V and E): keys are relative, so a **belief / desired** model; the worker
  thread presses keys until belief matches desired, respecting lid stroke time and wake beeps.
  Beliefs persist in `state-<id>.json`. It only needs channels with `init`, `press`, `auto_on` and
  `.bus.reset()`: `vanturtle.Channel` over `/dev/i2c`, or `vtboard.BoardChannel` over MQTT.
- `vtboard.py` (option E): each press is one QoS 0 message with a `seq`, answered by the ESP32 after
  release. A press without answer is resent with the **same seq**, also after an outage when the
  worker wants the same key again; the ESP32 (`archive/firmware/vanturtle_relay.h`) repeats answers
  instead of pressing twice. Beeps are never remembered on either side, so outages cannot push a
  real key out of the ESP32's memory (a stress test found that bug). Online = retained `status`
  online, a `state`/`done` within 35 s, and `i2c` true.
- `vtwifi.py` (option W): the controller uses one retained topic per field for state *and* commands.
  So: drop our own echoes; a touch becomes a *wish* shown until the controller reports it; **one
  command in flight**, sent only after `quiet_s` of controller silence (its echo-suppress window drops
  everything); `on` and `speed` resent once, `dir`, `lid` and `auto` never (toggles, or maybe:
  VanTurtle documents neither); never re-send after a report (don't fight the keypad); leave Auto
  first; lid is a persisted belief, assumed closed on the first start; online = a live
  (non-retained) message within 150 s. `swap_direction` flips dir 0/1 (VanTurtle: "0 = maybe
  forward"). Source: https://vanturtle.com/vtsc-docs/smart-controller-wifi-firmware/
- **Closing the lid switches the fan off** (owner's rule): `Fan._stop_before_closing` sends `on 0`
  before every `lid 0`, from the GUI and from presets, for every backend; opening the lid starts
  nothing. Presets therefore refuse `intake/exhaust N closed`.
- Presets: `[preset <key>]` sections, one line per fan (`exhaust 80`, `off closed`, `auto`, `keep`…,
  `parse_target`). Applied through `Fan.command`, which behaves like a GUI touch. *Save as* writes
  only that preset to `presets.json`, which overrides `config.ini`.
- Card order: gui-v2 sorts switch-pane cards alphabetically by title (`SortedIOChannelGroupModel`),
  nothing else. The presets card is "Alle fans" so it comes first (owner's wish; test_presets
  checks). A card's title is its outputs' `Settings/Group`, persisted in localsettings when the
  card first appears, so a later `name =` change in config.ini does not rename an existing card.
- Card texts: `TEXTS[language]` (`en`, `nl`) and `outputs_in()`; `[gui] language` picks one, default
  `en`. Every language must have every key (test_driver checks). Preset words in `config.ini`
  (`exhaust`, `off`…) and preset keys stay English; only `name =` lines are shown.
- `config.ini` sections `mqtt`, `presets`, `gui` and `preset …` are not fans. `main()` and
  `test_presets.test_shipped_config` filter them; keep them in sync. The shipped file is
  `config.default.ini`; tests read that.

## Tests

`test_driver.load_driver()` installs fake `dbus`, `gi.repository.GLib`, `vedbus`, `settingsdevice`
and `paho` modules and loads the driver from its path (the filename has dashes). Other tests reuse
it. Backends are tested against simulators: `SimFan` (test_vanturtle) and `Broker` + `SimController`
(test_vtwifi, which models VanTurtle's documented MQTT behaviour, direction both as toggle and
absolute, and lost messages). Time is a fake clock, never sleep. Temp files go in `.build/test-tmp`.
`test_vtwifi.test_random_sequences` and `test_vtboard.test_random_lossy_link(seeds=…)` are property
tests; when changing option W or E logic, also run them with a few thousand more seeds.
When adding behaviour, add a mutant to `mutation_check.py` that a test must catch; `e_source` mutates
`vtboard.py` source text and fails loudly if the text no longer matches.

## Other parts

- `archive/firmware/`: ESPHome YAML for options A and C (`common.yaml` shared via `packages:`,
  implements the MQTT contract; `maxxfan_packet.h` also compiled by `archive/tests/test_packet.cpp`)
  and E (`vanturtle-board.yaml`, `vanturtle_board.h`, `vanturtle_relay.h`; the last is plain C++
  tested by `archive/tests/test_relay.cpp`). ESPHome declares globals before it includes headers,
  so custom types live in header statics.
- `docs/ui.md`: card layout and behaviour (Dutch names). `docs/gui-mockup/project/` is a local copy
  of the owner's claude.ai Design artifact (https://claude.ai/artifact/URemBE8xJgGaqg2khCpj6J);
  keep both in step when the cards change.
- Docs are written for the van owner, not for developers: plain language, concrete steps, and say
  which facts are unverified.
