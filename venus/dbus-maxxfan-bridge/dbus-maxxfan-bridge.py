#!/usr/bin/env python3
"""dbus-maxxfan-bridge: show MaxxFans on the Venus OS switch pane.

One com.victronenergy.switch.maxxfan_<id> service per fan listed in config.ini. Each fan
has a backend:
  mqtt       an ESP32 node (hardware options A and C, archive/docs/mqtt-contract.md). The node's
             retained state topics are the only source of what the GUI shows.
  vanturtle  a VanTurtle board on this device's I2C bus (hardware option V, vanturtle.py).
  vanturtle-esp32
             a VanTurtle board at the fan with an ESP32 beside it that relays key presses
             over MQTT (hardware option E, vtboard.py); the key logic is vanturtle.py's.
  vanturtle-wifi
             a VanTurtle Smart Controller in the fan, WiFi firmware, over the same MQTT
             broker with VanTurtle's own topics (hardware option W, vtwifi.py).

Optionally one more card, com.victronenergy.switch.maxxfan_presets, with a button per preset
from config.ini ([preset <name>] sections) that sets all fans at once.

    dbus-maxxfan-bridge.py [--data-dir DIR]

DIR holds config.ini, the state-<fan>.json beliefs and presets.json (and, if Venus OS lacks
it, a copy of the pure-Python paho package); by default this script's own folder. Installed by SetupHelper, the service passes /data/setupOptions/MaxxFanBridge,
which package updates leave alone. A missing config.ini is created there from
config.default.ini.
"""

import argparse
import shutil

import configparser
import json
import logging
import os
import re
import sys
import time

for _p in (
    "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python",
    "/opt/victronenergy/velib_python",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "velib_python"),
):
    if os.path.isdir(_p):
        sys.path.insert(1, _p)
        break

import dbus  # noqa: E402
import dbus.mainloop.glib  # noqa: E402
from gi.repository import GLib  # noqa: E402
from settingsdevice import SettingsDevice  # noqa: E402
from vedbus import VeDbusService  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = HERE  # main() may point it elsewhere (--data-dir)


def package_version():
    """The SetupHelper package version (the `version` file two levels up), without the v."""
    try:
        with open(os.path.join(HERE, os.pardir, os.pardir, "version")) as f:
            return f.readline().strip().lstrip("v") or "dev"
    except OSError:
        return "dev"


VERSION = package_version()
log = logging.getLogger("dbus-maxxfan-bridge")

TOGGLE, DIMMER, SETPOINT, DROPDOWN, SLIDER = 1, 2, 3, 6, 7
STATUS_OFF, STATUS_ON = 0x00, 0x09
MODULE_CONNECTED = 0x100
ECHO_TIMEOUT_S = 5

# key, label, default type, allowed types, mqtt key, (min, max, step, unit) or None, labels or None
OUTPUTS = (
    ("fan", "Fan", TOGGLE, (TOGGLE,), "on", None, None),
    ("speed", "Speed", SLIDER, (DIMMER, SLIDER), "speed", (10, 100, 10, "%"), None),
    ("direction", "Direction", DROPDOWN, (DROPDOWN,), "dir", (0, 1, 1, None), ["Intake", "Exhaust"]),
    ("lid", "Lid", TOGGLE, (TOGGLE,), "lid", None, None),
    ("mode", "Mode", DROPDOWN, (DROPDOWN,), "mode", (0, 1, 1, None), ["Manual", "Auto"]),
    ("setpoint", "Auto setpoint", SETPOINT, (SETPOINT, SLIDER), "setpoint", (-2, 37, 1, None), None),
)
BY_KEY = {o[0]: o for o in OUTPUTS}
BY_MQTT = {o[4]: o for o in OUTPUTS}
ALL_KEYS = tuple(BY_KEY)
VANTURTLE_KEYS = ("fan", "speed", "direction", "lid", "mode")  # keys cannot set a setpoint
# What the cards say, per [gui] language in config.ini. gui-v2 draws the rest (On/Off, menus)
# in the language chosen in Venus OS itself.
TEXTS = {
    "en": {"fan": "Fan", "speed": "Speed", "direction": "Direction", "lid": "Lid", "mode": "Mode",
           "setpoint": "Auto setpoint", "direction_labels": ["Intake", "Exhaust"],
           "mode_labels": ["Manual", "Auto"], "save": "Save as", "presets": "Fan presets"},
    "nl": {"fan": "Ventilator", "speed": "Snelheid", "direction": "Richting", "lid": "Klep open",
           "mode": "Modus", "setpoint": "Thermostaat", "direction_labels": ["Inblazen", "Afzuigen"],
           "mode_labels": ["Handmatig", "Automatisch"], "save": "Opslaan als", "presets": "Alle fans"},
}


def outputs_in(language, keys=ALL_KEYS):
    """OUTPUTS for these keys, with names and menu entries in that language."""
    t = TEXTS[language]
    return [(key, t[key], otype, valid, mk, dim, t.get(key + "_labels", labels) if labels else None)
            for key, _label, otype, valid, mk, dim, labels in OUTPUTS if key in keys]


# Settings the user may change from the GUI, persisted in com.victronenergy.settings.
PERSISTED = {"CustomName": "name", "Group": "group", "ShowUIControl": "show", "Type": "type"}


def snap(value, low, high, step):
    """Clamp to [low, high] and round to the nearest step counted from low."""
    value = max(low, min(high, float(value)))
    return int(low + round((value - low) / step) * step)


class PrivateSystemBus(dbus.bus.BusConnection):
    """A separate connection per service, so one process can own several names."""

    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SYSTEM)


def switch_service(bus, service_name, base, name, instance, outputs, on_write, connection,
                   product, serial):
    """A com.victronenergy.switch service (not yet registered) with one SwitchableOutput per
    entry of outputs, plus the settings that keep what the user edits in the GUI (names,
    groups, visibility, control types). Returns (service, settings)."""
    entries = {
        "instance": [base + "/ClassAndVrmInstance", "switch:%d" % instance, 0, 0],
        "customname": [base + "/CustomName", name, 0, 0],
    }
    for key, _label, otype, _valid, _mk, _dim, _labels in outputs:
        entries[key + "_name"] = ["%s/%s/CustomName" % (base, key), "", 0, 0]
        entries[key + "_group"] = ["%s/%s/Group" % (base, key), name, 0, 0]
        entries[key + "_show"] = ["%s/%s/ShowUIControl" % (base, key), 1, 0, 15]
        entries[key + "_type"] = ["%s/%s/Type" % (base, key), otype, 0, 13]
    settings = SettingsDevice(bus, entries, eventCallback=None, timeout=10)

    stored = str(settings["instance"]).split(":")
    if len(stored) == 2 and stored[0] == "switch" and stored[1].isdigit():
        instance = int(stored[1])
    else:
        settings["instance"] = "switch:%d" % instance

    def on_custom_name(_path, value):
        settings["customname"] = str(value)
        return True

    svc = VeDbusService(service_name, bus=bus, register=False)
    svc.add_path("/Mgmt/ProcessName", os.path.basename(__file__))
    svc.add_path("/Mgmt/ProcessVersion", VERSION)
    svc.add_path("/Mgmt/Connection", connection)
    svc.add_path("/DeviceInstance", instance)
    svc.add_path("/ProductId", 0xFFFF)
    svc.add_path("/ProductName", product)
    svc.add_path("/CustomName", settings["customname"], writeable=True, onchangecallback=on_custom_name)
    svc.add_path("/FirmwareVersion", VERSION)
    svc.add_path("/HardwareVersion", None)
    svc.add_path("/Serial", serial)
    svc.add_path("/Connected", 0)
    svc.add_path("/State", 0)

    for key, label, otype, valid, _mk, dim, labels in outputs:
        p = "/SwitchableOutput/%s/" % key
        current_type = settings[key + "_type"]
        if current_type not in valid:
            current_type = otype
        svc.add_path(p + "Name", label)
        svc.add_path(p + "State", 1 if dim else 0, writeable=True, onchangecallback=on_write)
        svc.add_path(p + "Status", STATUS_ON if dim else STATUS_OFF)
        svc.add_path(p + "Settings/Type", current_type, writeable=True, onchangecallback=on_write)
        svc.add_path(p + "Settings/ValidTypes", sum(1 << t for t in valid))
        svc.add_path(p + "Settings/CustomName", settings[key + "_name"], writeable=True,
                     onchangecallback=on_write)
        svc.add_path(p + "Settings/Group", settings[key + "_group"], writeable=True,
                     onchangecallback=on_write)
        svc.add_path(p + "Settings/ShowUIControl", settings[key + "_show"], writeable=True,
                     onchangecallback=on_write)
        if dim:
            low, high, step, unit = dim
            svc.add_path(p + "Dimming", low, writeable=True, onchangecallback=on_write)
            svc.add_path(p + "Settings/DimmingMin", low)
            svc.add_path(p + "Settings/DimmingMax", high)
            svc.add_path(p + "Settings/StepSize", step)
            svc.add_path(p + "Settings/Decimals", 0)
            if unit:
                svc.add_path(p + "Settings/Unit", unit)
        if labels:
            svc.add_path(p + "Settings/Labels", labels)
    return svc, settings


def write_setting(settings, key, sub, value, valid):
    """A GUI edit of an output's Settings/<name>. False if the value is not allowed."""
    name = sub[len("Settings/"):]
    if name == "Type" and value not in valid:
        return False
    settings[key + "_" + PERSISTED[name]] = value
    return True


class Fan:
    def __init__(self, fan_id, name, instance, publish, bus, keys=ALL_KEYS, connection=None,
                 language="en"):
        self.id = fan_id
        self.publish = publish  # publish(fan_id, mqtt_key, int_value)
        self.keys = tuple(keys)
        self.outputs = outputs_in(language, keys)
        self.online = False
        self.node = {}  # last value reported by the node, per mqtt key
        self.on_touch = None  # called with the fan id after each control touched on the screen
        self._resync_timer = None
        self._last_sent = None  # (mqtt key, value) of the last command

        self.svc, self.settings = switch_service(
            bus, "com.victronenergy.switch.maxxfan_%s" % fan_id, "/Settings/Devices/maxxfan_%s" % fan_id,
            name, instance, self.outputs, self._on_write, connection or "MQTT maxxfan/%s" % fan_id,
            "MaxxFan", "maxxfan-%s" % fan_id)
        # Ceiling temperature (option C nodes) is shown next to the setpoint by the GUI.
        if "setpoint" in keys:
            self.svc.add_path("/SwitchableOutput/setpoint/Measurement", None)
        self.svc.register()

    # ---- GUI -> node -------------------------------------------------------

    def _on_write(self, path, value):
        _, _, key, sub = path.split("/", 3)
        _k, _label, _otype, valid, mqtt_key, dim, _labels = BY_KEY[key]

        if sub.startswith("Settings/"):
            return write_setting(self.settings, key, sub, value, valid)

        if sub == "State" and dim:
            return int(value) == 1  # ranged controls are always "on"; the value lives in Dimming
        if not self.online:
            log.warning("%s: %s refused, node offline", self.id, path)
            return False

        if sub == "State":
            wanted = 1 if value else 0
            self.svc["/SwitchableOutput/%s/Status" % key] = STATUS_ON if wanted else STATUS_OFF
        else:  # Dimming
            low, high, step, _unit = dim
            wanted = snap(value, low, high, step)
        if key == "lid" and wanted == 0:
            self._stop_before_closing()
        self._send(mqtt_key, wanted)
        self._arm_resync()
        if sub == "Dimming" and wanted != value:
            GLib.idle_add(self._set, path, wanted)  # show the snapped value
        if self.on_touch:
            self.on_touch(self.id)
        return True

    def command(self, key, value):
        """Send one control's value as a touch on the screen would (used by presets)."""
        if key not in self.keys or not self.online:
            return False
        _k, _label, _otype, _valid, mqtt_key, dim, _labels = BY_KEY[key]
        value = snap(value, *dim[:3]) if dim else (1 if value else 0)
        if key == "lid" and value == 0:
            self._stop_before_closing()
        self._send(mqtt_key, value)
        self._arm_resync()
        self._show(mqtt_key, value)
        return True

    def _stop_before_closing(self):
        """Closing the lid switches the fan off first, so it never runs against a closed lid.
        Sent even when the card already shows it off: the command is absolute, so it is also
        right when the card is wrong (keypad, remote). Opening the lid starts nothing."""
        if "fan" not in self.keys:
            return
        if self._last_sent == ("on", 0) and self.svc["/SwitchableOutput/fan/State"] == 0:
            return  # just sent (a preset's "off closed"), and nothing has started it since
        self._send("on", 0)
        self._show("on", 0)

    def _send(self, mqtt_key, value):
        self.publish(self.id, mqtt_key, value)
        self._last_sent = (mqtt_key, value)

    def snapshot(self):
        """What the card shows now: {control key: value}."""
        return {o[0]: self.svc["/SwitchableOutput/%s/%s" % (o[0], "Dimming" if o[5] else "State")]
                for o in self.outputs}

    def _arm_resync(self):
        if self._resync_timer is not None:
            GLib.source_remove(self._resync_timer)
        self._resync_timer = GLib.timeout_add_seconds(ECHO_TIMEOUT_S, self._resync)

    def _resync(self):
        """A while after a command, fall back to whatever the node last reported."""
        self._resync_timer = None
        for mqtt_key, value in self.node.items():
            self._show(mqtt_key, value)
        return False

    def _set(self, path, value):
        self.svc[path] = value
        return False

    # ---- node -> GUI -------------------------------------------------------

    def set_online(self, online):
        if online == self.online:
            return
        self.online = online
        self.svc["/Connected"] = 1 if online else 0
        self.svc["/State"] = MODULE_CONNECTED if online else 0
        log.info("%s: node %s", self.id, "online" if online else "offline")

    def on_state(self, mqtt_key, payload):
        if mqtt_key == "temp":
            if "setpoint" not in self.keys:
                return
            try:
                self.svc["/SwitchableOutput/setpoint/Measurement"] = round(float(payload), 1)
            except ValueError:
                pass
            return
        if mqtt_key not in BY_MQTT or BY_MQTT[mqtt_key] not in self.outputs:
            return
        try:
            value = int(float(payload))
        except ValueError:
            log.warning("%s: bad payload %r for %s", self.id, payload, mqtt_key)
            return
        self.node[mqtt_key] = value
        self._show(mqtt_key, value)

    def _show(self, mqtt_key, value):
        key, _label, _otype, _valid, _mk, dim, _labels = BY_MQTT[mqtt_key]
        p = "/SwitchableOutput/%s/" % key
        if dim:
            low, high, step, _unit = dim
            self.svc[p + "Dimming"] = snap(value, low, high, step)
        else:
            self.svc[p + "State"] = 1 if value else 0
            self.svc[p + "Status"] = STATUS_ON if value else STATUS_OFF


# ---- presets ------------------------------------------------------------------

PRESET_ORDER = ("mode", "fan", "lid", "direction", "speed")  # leave Auto first, speed last
PRESET_SETTLE_S = 60  # after this long, a preset whose fans have drifted is no longer lit


def parse_target(text):
    """What one fan does in a preset -> {control key: value}, or None for "keep".

    off [open|closed]                 fan off; lid left alone unless given
    intake|exhaust <10..100> [open]   running, lid open (a closed lid always means off)
    auto                              the fan's own thermostat
    keep                              this fan is not touched
    """
    words = text.lower().replace("%", " ").split()
    if words == ["keep"]:
        return None
    if words == ["auto"]:
        return {"mode": 1}
    if not words:
        raise ValueError("empty")
    head, rest = words[0], words[1:]
    if head == "off":
        target = {"mode": 0, "fan": 0}
    elif head in ("intake", "exhaust"):
        if not rest or not rest[0].isdigit() or int(rest[0]) not in range(10, 101, 10):
            raise ValueError("%r: speed must be 10, 20 ... 100" % text)
        target = {"mode": 0, "fan": 1, "direction": 1 if head == "exhaust" else 0,
                  "speed": int(rest.pop(0)), "lid": 1}
    else:
        raise ValueError("%r: expected off, intake, exhaust, auto or keep" % text)
    if rest:
        if rest not in (["open"], ["closed"]):
            raise ValueError("%r: only open or closed may follow" % text)
        if target["fan"] and rest == ["closed"]:
            raise ValueError("%r: closing the lid switches the fan off; use off closed" % text)
        target["lid"] = 1 if rest[0] == "open" else 0
    return target


def format_target(shown):
    """The inverse: a card's current values as preset text."""
    if shown.get("mode") == 1:
        return "auto"
    lid = "" if shown.get("lid") is None else (" open" if shown["lid"] else " closed")
    if not shown.get("fan"):
        return "off" + lid
    return "%s %d open" % ("exhaust" if shown.get("direction") else "intake", shown.get("speed", 10))


def read_presets(cfg, fan_ids):
    """[preset <key>] sections -> [(key, label, {fan_id: target or None})], in file order."""
    presets = []
    for section in cfg.sections():
        if not section.lower().startswith("preset "):
            continue
        key = section[len("preset "):].strip().lower()
        if not re.match(r"^[a-z0-9_]{1,32}$", key) or key == "save":
            raise ValueError("[%s]: preset names are letters, digits and _" % section)
        unknown = set(cfg.options(section)) - {"name"} - set(fan_ids)
        if unknown:
            raise ValueError("[%s]: no fan called %s" % (section, ", ".join(sorted(unknown))))
        targets = {}
        for fan_id in fan_ids:
            try:
                targets[fan_id] = parse_target(cfg.get(section, fan_id, fallback="keep"))
            except ValueError as e:
                raise ValueError("[%s] %s: %s" % (section, fan_id, e))
        presets.append((key, cfg.get(section, "name", fallback=key.capitalize()), targets))
    return presets


class Presets:
    """A card with one toggle per preset and a "Save as" menu.

    Switching a preset on sends its values to every fan it names, exactly as touching their
    cards would, and lights it (the others go dark). It goes dark again when someone touches a
    control of one of its fans, or when its fans no longer show its values a minute after it
    was applied (keypad, remote, thermostat). Switching it off only darkens it.
    "Save as" stores what the fan cards show now into a preset, kept in a JSON file that
    overrides config.ini for that preset.
    """

    def __init__(self, presets, fans, bus, instance=62, name=None, store=None,
                 clock=time.monotonic, language="en"):
        name = name or TEXTS[language]["presets"]
        self.order = [key for key, _label, _t in presets]
        self.labels = {key: label for key, label, _t in presets}
        self.targets = {key: dict(t) for key, _label, t in presets}
        self.fans, self.store, self.clock = fans, store, clock
        self.active = self.applied_at = None
        self._load()

        self.outputs = [(key, self.labels[key], TOGGLE, (TOGGLE,), None, None, None) for key in self.order]
        self.outputs.append(("save", TEXTS[language]["save"], DROPDOWN, (DROPDOWN,), None, (0, len(self.order), 1, None),
                             ["—"] + [self.labels[k] for k in self.order]))
        self.by_key = {o[0]: o for o in self.outputs}
        self.svc, self.settings = switch_service(
            bus, "com.victronenergy.switch.maxxfan_presets", "/Settings/Devices/maxxfan_presets",
            name, instance, self.outputs, self._on_write, "Presets for %s" % ", ".join(fans),
            "MaxxFan presets", "maxxfan-presets")
        self.svc["/Connected"] = 1
        self.svc["/State"] = MODULE_CONNECTED
        self.svc.register()
        for fan in fans.values():
            fan.on_touch = self._touched

    def _on_write(self, path, value):
        _, _, key, sub = path.split("/", 3)
        _k, _label, _otype, valid, _mk, dim, _labels = self.by_key[key]
        if sub.startswith("Settings/"):
            return write_setting(self.settings, key, sub, value, valid)
        if key == "save":
            if sub == "State":
                return int(value) == 1
            index = int(value)
            if 1 <= index <= len(self.order):
                self.save(self.order[index - 1])
            GLib.idle_add(self._set, path, 0)  # a menu of actions: back to "—"
            return True
        if value:
            return self.apply(key)
        if self.active == key:
            self._light(None)
        return True

    def apply(self, key):
        sent = False
        for fan_id, target in self.targets[key].items():
            fan = self.fans.get(fan_id)
            if target is None or fan is None:
                continue
            if not fan.online:
                log.warning("preset %s: %s is offline, left alone", key, fan_id)
                continue
            shown = fan.snapshot()
            for k in PRESET_ORDER:
                if k not in target:
                    continue
                if k == "mode" and target[k] == 0 and shown.get("mode") != 1:
                    continue  # not in Auto: nothing to leave
                fan.command(k, target[k])
            sent = True
        if not sent:
            log.warning("preset %s: no fan reachable", key)
            return False
        log.info("preset %s applied", key)
        self._light(key)
        return True

    def save(self, key):
        for fan_id, fan in self.fans.items():
            if fan.online:
                self.targets[key][fan_id] = parse_target(format_target(fan.snapshot()))
        self._store(key)
        log.info("preset %s saved: %s", key, self.texts(key))
        self._light(key)

    def texts(self, key):
        return {fan_id: "keep" if t is None else format_target(t) for fan_id, t in self.targets[key].items()}

    def _touched(self, fan_id):
        if self.active and self.targets[self.active].get(fan_id) is not None:
            self._light(None)

    def tick(self):
        """Darken a lit preset whose fans have drifted away from it."""
        if self.active and self.clock() - self.applied_at >= PRESET_SETTLE_S:
            for fan_id, target in self.targets[self.active].items():
                fan = self.fans.get(fan_id)
                if target is None or fan is None or not fan.online:
                    continue
                shown = fan.snapshot()
                if any(shown.get(k) != v for k, v in target.items() if k in fan.keys):
                    log.info("preset %s no longer matches %s", self.active, fan_id)
                    self._light(None)
                    break
        return True

    def _light(self, key):
        self.active = key
        self.applied_at = self.clock() if key else None
        for k in self.order:
            on = 1 if k == key else 0
            self.svc["/SwitchableOutput/%s/State" % k] = on
            self.svc["/SwitchableOutput/%s/Status" % k] = STATUS_ON if on else STATUS_OFF

    def _set(self, path, value):
        self.svc[path] = value
        return False

    # ---- presets saved from the screen ------------------------------------------

    def _load(self):
        if not self.store:
            return
        try:
            with open(self.store) as f:
                saved = json.load(f)
        except (OSError, ValueError):
            return
        for key, texts in saved.items():
            if key not in self.targets or not isinstance(texts, dict):
                continue
            for fan_id, text in texts.items():
                if fan_id in self.fans:
                    try:
                        self.targets[key][fan_id] = parse_target(str(text))
                    except ValueError as e:
                        log.warning("%s: ignoring preset %s for %s: %s", self.store, key, fan_id, e)

    def _store(self, key):
        """Only the preset saved from the screen goes in the file; the others keep following
        config.ini."""
        if not self.store:
            return
        saved = {}
        try:
            with open(self.store) as f:
                saved = json.load(f)
        except (OSError, ValueError):
            pass
        saved[key] = self.texts(key)
        try:
            tmp = self.store + ".tmp"
            with open(tmp, "w") as f:
                json.dump(saved, f, indent=1, sort_keys=True)
            os.replace(tmp, self.store)
        except OSError as e:
            log.warning("cannot save presets: %s", e)


class Bridge:
    """Routes MQTT messages (paho thread) to the fans (GLib main loop) and back.

    fans: ESP32 nodes by id (archive/docs/mqtt-contract.md). vt: everything else that owns a topic
    prefix, with on_message(leaf, payload, retained), broker_lost() and tick(): VanTurtle WiFi
    controllers (vtwifi.py) and the ESP32 relays of VanTurtle boards (vtboard.py).
    """

    def __init__(self, fans, client, vt=None):
        self.fans = fans
        self.vt = vt if vt is not None else {}
        self.client = client
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message

    def publish(self, fan_id, mqtt_key, value):
        self.client.publish("maxxfan/%s/set/%s" % (fan_id, mqtt_key), str(value), qos=1)

    def publish_raw(self, topic, payload, qos=1):
        self.client.publish(topic, payload, qos=qos)

    def _on_connect(self, client, *_args):
        log.info("MQTT connected")
        topics = [("maxxfan/+/status", 1), ("maxxfan/+/state/#", 1)]
        client.subscribe(topics + [(prefix + "/#", 1) for prefix in sorted(self.vt)])

    def _on_disconnect(self, *_args):
        log.warning("MQTT disconnected")
        GLib.idle_add(self._all_offline)

    def _all_offline(self):
        for fan in self.fans.values():
            fan.set_online(False)
        for worker in self.vt.values():
            worker.broker_lost()
        return False

    def _on_message(self, _client, _userdata, msg):
        GLib.idle_add(self.dispatch, msg.topic, msg.payload.decode("utf-8", "replace").strip(),
                      bool(getattr(msg, "retain", False)))

    def tick(self):
        for worker in self.vt.values():
            worker.tick()
        return True

    def dispatch(self, topic, payload, retained=False):
        for prefix, worker in self.vt.items():
            if topic.startswith(prefix + "/"):
                worker.on_message(topic[len(prefix) + 1:], payload, retained)
                return False
        parts = topic.split("/")
        if len(parts) >= 3 and parts[0] == "maxxfan" and parts[1] in self.fans:
            fan = self.fans[parts[1]]
            if parts[2] == "status" and len(parts) == 3:
                fan.set_online(payload == "online")
            elif parts[2] == "state" and len(parts) == 4:
                fan.on_state(parts[3], payload)
        return False


def make_client():
    import paho.mqtt.client as mqtt  # only needed when a fan uses the mqtt backend
    try:  # paho-mqtt 2.x
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="dbus-maxxfan-bridge")
    except AttributeError:  # paho-mqtt 1.x
        return mqtt.Client(client_id="dbus-maxxfan-bridge")


def language(cfg):
    value = cfg.get("gui", "language", fallback="en").strip().lower()
    if value not in TEXTS:
        raise ValueError("[gui] language = %r, expected one of %s" % (value, ", ".join(sorted(TEXTS))))
    return value


def tristate(cfg, section, option):
    """yes / no / anything else (unknown, the default) -> True / False / None."""
    value = cfg.get(section, option, fallback="unknown").strip().lower()
    return {"yes": True, "true": True, "1": True, "no": False, "false": False, "0": False}.get(value)


def topic_prefix(cfg, section, leaf):
    prefix = cfg.get(section, "topic", fallback="maxxfan/%s/%s" % (section, leaf)).strip().rstrip("/")
    if not prefix or "+" in prefix or "#" in prefix:
        raise ValueError("%s: bad topic %r" % (section, prefix))
    return prefix


def vanturtle_worker(section, cfg, fan, rj45, rj11, post):
    """The VanTurtle key logic (vanturtle.py) behind a Fan, for options V and E."""
    import vanturtle

    worker = vanturtle.VanTurtleFan(
        section, rj45, rj11, post, fan.on_state, fan.set_online,
        state_file=os.path.join(DATA_DIR, "state-%s.json" % section),
        onoff_s=cfg.getfloat(section, "onoff_press_s", fallback=0.75),
        wake_beep=cfg.getboolean(section, "wake_beep", fallback=True),
        on_opens_lid=tristate(cfg, section, "on_opens_lid"),
        rj11_off_closes_lid=tristate(cfg, section, "rj11_off_closes_lid"),
        lid_settle_s=cfg.getfloat(section, "lid_settle_s", fallback=12.0),
    )

    def send(_fan_id, key, value):
        worker.command(key, value)
        fan.on_state(key, str(value))  # show the target now; the worker gets there in its own time

    fan.publish = send
    return worker


def make_vanturtle_fan(section, cfg, buses, bus, instance, post=GLib.idle_add):
    """Option V: a Fan on D-Bus, the VanTurtle worker, and the board on this device's I2C bus."""
    import vanturtle

    number = cfg.getint(section, "i2c_bus", fallback=1)
    i2c = buses.setdefault(number, vanturtle.I2CBus(number))
    rj45 = vanturtle.Channel(i2c, *vanturtle.parse_channel(cfg.get(section, "rj45")))
    rj11 = None
    if cfg.get(section, "rj11", fallback=""):
        rj11 = vanturtle.Channel(i2c, *vanturtle.parse_channel(cfg.get(section, "rj11")))
    fan = Fan(section, cfg.get(section, "name", fallback=section), instance, None, bus,
              keys=VANTURTLE_KEYS, connection="VanTurtle I2C %s" % rj45, language=language(cfg))
    return fan, vanturtle_worker(section, cfg, fan, rj45, rj11, post)


def make_vtboard_fan(section, cfg, bus, instance, publish_raw, post=GLib.idle_add, **link_options):
    """Option E: a Fan on D-Bus, the VanTurtle worker, and the board at the fan reached through
    the ESP32 beside it. Returns (fan, worker, link); the link goes to the Bridge."""
    import vtboard

    prefix = topic_prefix(cfg, section, "board")
    link = vtboard.BoardLink(prefix, lambda topic, payload: publish_raw(topic, payload, qos=0),
                             **link_options)  # qos 0: a press must never be delivered late

    def port(option, fallback):
        text = cfg.get(section, option, fallback=fallback).strip()
        if text not in ("1", "2"):
            raise ValueError("%s: %s = %r, expected the board port 1 or 2" % (section, option, text))
        return vtboard.BoardChannel(link, int(text))

    rj45 = port("rj45", "1")
    rj11 = port("rj11", "") if cfg.get(section, "rj11", fallback="").strip() else None
    if rj11 and rj11.number == rj45.number:
        raise ValueError("%s: rj45 and rj11 cannot both be port %d" % (section, rj45.number))
    fan = Fan(section, cfg.get(section, "name", fallback=section), instance, None, bus,
              keys=VANTURTLE_KEYS, connection="VanTurtle board via WiFi, %s" % prefix,
              language=language(cfg))
    return fan, vanturtle_worker(section, cfg, fan, rj45, rj11, post), link


def make_vtwifi_fan(section, cfg, bus, instance, publish_raw, clock=None):
    """A Fan on D-Bus plus the VanTurtle WiFi controller model behind it."""
    import vtwifi

    prefix = topic_prefix(cfg, section, "vt")
    fan = Fan(section, cfg.get(section, "name", fallback=section), instance, None, bus,
              keys=VANTURTLE_KEYS, connection="VanTurtle WiFi %s" % prefix, language=language(cfg))
    extra = {"clock": clock} if clock else {}
    worker = vtwifi.VtWifiFan(
        section, prefix, publish_raw, lambda key, value: fan.on_state(key, str(value)), fan.set_online,
        state_file=os.path.join(DATA_DIR, "state-%s.json" % section),
        on_opens_lid=tristate(cfg, section, "on_opens_lid"),
        lid_settle_s=cfg.getfloat(section, "lid_settle_s", fallback=12.0),
        confirm_s=cfg.getfloat(section, "confirm_s", fallback=10.0),
        quiet_s=cfg.getfloat(section, "quiet_s", fallback=2.0),
        dir_swapped=cfg.getboolean(section, "swap_direction", fallback=False),
        **extra)
    fan.publish = lambda _fan_id, key, value: worker.command(key, value)
    return fan, worker


def add_prefix(handlers, prefix, handler):
    """Each topic prefix belongs to one fan; none may lie inside another."""
    for p in handlers:
        if p == prefix or p.startswith(prefix + "/") or prefix.startswith(p + "/"):
            raise ValueError("topic %s overlaps %s" % (prefix, p))
    handlers[prefix] = handler


def prepare_data_dir(data_dir):
    """Make sure data_dir/config.ini exists (copied from config.default.ini); return its path."""
    path = os.path.join(data_dir, "config.ini")
    if not os.path.exists(path):
        os.makedirs(data_dir, exist_ok=True)
        shutil.copyfile(os.path.join(HERE, "config.default.ini"), path)
        log.info("created %s from the defaults; edit it and restart the service", path)
    return path


def main(argv=None):
    global DATA_DIR
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="MaxxFan cards for the Venus OS switch pane")
    parser.add_argument("--data-dir", default=HERE,
                        help="folder with config.ini, beliefs and saved presets (default: %(default)s)")
    args = parser.parse_args(argv)
    DATA_DIR = os.path.abspath(args.data_dir)
    sys.path.append(DATA_DIR)  # a paho-mqtt copied there survives package updates
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    try:
        config_path = prepare_data_dir(DATA_DIR)
        cfg.read(config_path)
    except (OSError, configparser.Error) as e:
        log.error("config.ini: %s", e)
        return 1
    try:
        lang = language(cfg)
    except ValueError as e:
        log.error("config.ini: %s", e)
        return 1

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    mqtt_fans, links, workers, buses, used = {}, {}, [], {}, set()
    all_fans = {}
    client = bridge = None
    for section in cfg.sections():
        if section in ("mqtt", "presets", "gui") or section.lower().startswith("preset "):
            continue
        backend = cfg.get(section, "backend", fallback="mqtt")
        instance = cfg.getint(section, "instance", fallback=60 + len(used))
        if backend in ("mqtt", "vanturtle-wifi", "vanturtle-esp32") and client is None:
            client = make_client()
            bridge = Bridge(mqtt_fans, client, links)
        try:
            if backend == "vanturtle":
                fan, worker = make_vanturtle_fan(section, cfg, buses, PrivateSystemBus(), instance)
                channels = [str(c) for c in (worker.rj45, worker.rj11) if c]
                if used & set(channels):
                    raise ValueError("VanTurtle channel %s is used by another fan" % channels)
                used.update(channels)
                workers.append(worker)
            elif backend == "vanturtle-esp32":
                fan, worker, link = make_vtboard_fan(section, cfg, PrivateSystemBus(), instance,
                                                     bridge.publish_raw)
                add_prefix(links, link.prefix, link)
                workers.append(worker)
            elif backend == "vanturtle-wifi":
                fan, worker = make_vtwifi_fan(section, cfg, PrivateSystemBus(), instance, bridge.publish_raw)
                add_prefix(links, worker.prefix, worker)
            elif backend == "mqtt":
                fan = mqtt_fans[section] = Fan(section, cfg.get(section, "name", fallback=section),
                                               instance, bridge.publish, PrivateSystemBus(),
                                               language=language(cfg))
            else:
                raise ValueError("unknown backend %r" % backend)
        except ValueError as e:
            log.error("%s: %s", section, e)
            return 1
        all_fans[section] = fan
        used.add("instance %d" % instance)
    if not used:
        log.error("no fans in config.ini")
        return 1

    presets = None
    try:
        preset_list = read_presets(cfg, list(all_fans))
    except ValueError as e:
        log.error("config.ini: %s", e)
        return 1
    if preset_list:
        instance = cfg.getint("presets", "instance", fallback=62)
        if "instance %d" % instance in used:
            log.error("[presets]: instance %d is used by a fan", instance)
            return 1
        presets = Presets(preset_list, all_fans, PrivateSystemBus(), instance,
                          cfg.get("presets", "name", fallback=None),
                          store=os.path.join(DATA_DIR, "presets.json"),
                          language=lang)
        GLib.timeout_add_seconds(5, presets.tick)

    for worker in workers:
        worker.start()
    if client is not None:
        if cfg.get("mqtt", "username", fallback=""):
            client.username_pw_set(cfg.get("mqtt", "username"), cfg.get("mqtt", "password", fallback=""))
        client.reconnect_delay_set(1, 30)
        client.connect_async(cfg.get("mqtt", "host", fallback="127.0.0.1"),
                             cfg.getint("mqtt", "port", fallback=1883), keepalive=30)
        client.loop_start()
    if links:
        GLib.timeout_add_seconds(1, bridge.tick)
    log.info("dbus-maxxfan-bridge %s started with %s, fans: %s; presets: %s", VERSION, config_path,
             ", ".join(all_fans), ", ".join(presets.order) if presets else "none")
    GLib.MainLoop().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
