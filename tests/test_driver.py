"""Desktop test of the Cerbo driver logic with stand-ins for D-Bus, GLib and MQTT.

    python3 tests/test_driver.py
"""
import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeService:
    def __init__(self, name, bus=None, register=True):
        self.name, self.paths, self.callbacks, self.registered = name, {}, {}, False

    def add_path(self, path, value, writeable=False, onchangecallback=None, **_kw):
        self.paths[path] = value
        if writeable:
            self.callbacks[path] = onchangecallback

    def register(self):
        self.registered = True

    def __getitem__(self, path):
        return self.paths[path]

    def __setitem__(self, path, value):
        assert path in self.paths, path
        self.paths[path] = value

    def gui_write(self, path, value):
        """What vedbus does when the GUI sets a value."""
        assert path in self.callbacks, "not writeable: " + path
        if value == self.paths[path]:
            return True  # vedbus returns early: the driver never hears about it
        accepted = self.callbacks[path](path, value)
        if accepted:
            self.paths[path] = value
        return accepted


class FakeSettings(dict):
    def __init__(self, bus, entries, eventCallback=None, timeout=0):
        super().__init__({k: v[1] for k, v in entries.items()})
        self.entries = entries


class FakeGLib:
    timers, idles, next_id = {}, [], 1

    @classmethod
    def timeout_add_seconds(cls, _s, fn):
        cls.next_id += 1
        cls.timers[cls.next_id] = fn
        return cls.next_id

    @classmethod
    def source_remove(cls, tid):
        cls.timers.pop(tid, None)

    @classmethod
    def idle_add(cls, fn, *args):
        cls.idles.append((fn, args))

    @classmethod
    def run_idles(cls):
        while cls.idles:
            fn, args = cls.idles.pop(0)
            fn(*args)

    @classmethod
    def fire_timers(cls):
        for tid in list(cls.timers):
            cls.timers.pop(tid)()


def install_fakes():
    def mod(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        sys.modules[name] = m
        return m

    bus = mod("dbus.bus", BusConnection=type("BusConnection", (), {"TYPE_SYSTEM": 1}))
    glib_loop = mod("dbus.mainloop.glib", DBusGMainLoop=lambda **k: None)
    mainloop = mod("dbus.mainloop", glib=glib_loop)
    mod("dbus", bus=bus, mainloop=mainloop)
    mod("gi")
    mod("gi.repository", GLib=FakeGLib)
    mod("paho")
    mod("paho.mqtt")
    mod("paho.mqtt.client", Client=object)
    mod("vedbus", VeDbusService=FakeService)
    mod("settingsdevice", SettingsDevice=FakeSettings)


def load_driver():
    install_fakes()
    sys.path.insert(0, os.path.join(ROOT, "venus", "dbus-maxxfan-bridge"))
    path = os.path.join(ROOT, "venus", "dbus-maxxfan-bridge", "dbus-maxxfan-bridge.py")
    spec = importlib.util.spec_from_file_location("driver", path)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    return driver


def main():
    d = load_driver()
    sent = []
    fan = d.Fan("fan1", "Galley fan", 60, lambda *a: sent.append(a), bus=None)
    svc = fan.svc
    bridge = d.Bridge({"fan1": fan}, types.SimpleNamespace())
    out = "/SwitchableOutput/"

    # Service shape
    assert svc.name == "com.victronenergy.switch.maxxfan_fan1" and svc.registered
    assert svc["/DeviceInstance"] == 60 and svc["/Connected"] == 0
    assert svc[out + "speed/Settings/Type"] == 7
    assert svc[out + "speed/Settings/ValidTypes"] == (1 << 2) | (1 << 7)
    assert svc[out + "direction/Settings/Labels"] == ["Intake", "Exhaust"]
    assert svc[out + "fan/Settings/Group"] == "Galley fan"
    assert out + "fan/Dimming" not in svc.paths

    # Offline: commands refused, settings still editable
    assert svc.gui_write(out + "fan/State", 1) is False and sent == []
    assert svc.gui_write(out + "lid/Settings/CustomName", "Lid open") is True
    assert fan.settings["lid_name"] == "Lid open"
    assert svc.gui_write(out + "speed/Settings/Type", 4) is False      # stepped not allowed
    assert svc.gui_write(out + "speed/Settings/Type", 2) is True and fan.settings["speed_type"] == 2

    # Node comes online and reports state
    bridge.dispatch("maxxfan/fan1/status", "online")
    assert svc["/Connected"] == 1 and svc["/State"] == 0x100
    for k, v in (("on", "1"), ("speed", "60"), ("dir", "1"), ("lid", "1"), ("mode", "0"), ("setpoint", "24")):
        bridge.dispatch("maxxfan/fan1/state/" + k, v)
    bridge.dispatch("maxxfan/fan1/state/temp", "23.44")
    bridge.dispatch("maxxfan/fan1/state/variant", "A")                 # ignored
    bridge.dispatch("maxxfan/fan9/state/on", "1")                      # unknown fan ignored
    bridge.dispatch("maxxfan/fan1/state/speed", "garbage")             # ignored
    assert svc[out + "fan/State"] == 1 and svc[out + "fan/Status"] == 0x09
    assert svc[out + "speed/Dimming"] == 60 and svc[out + "direction/Dimming"] == 1
    assert svc[out + "lid/State"] == 1 and svc[out + "setpoint/Dimming"] == 24
    assert svc[out + "setpoint/Measurement"] == 23.4

    # GUI commands go out as MQTT, snapped and clamped
    assert svc.gui_write(out + "fan/State", 0) is True
    assert svc.gui_write(out + "speed/Dimming", 74) is True
    assert svc.gui_write(out + "speed/Dimming", 3) is True
    assert svc.gui_write(out + "direction/Dimming", 0) is True
    assert svc.gui_write(out + "setpoint/Dimming", 50) is True
    assert svc.gui_write(out + "speed/State", 0) is False               # ranged controls cannot be "off"
    assert sent == [("fan1", "on", 0), ("fan1", "speed", 70), ("fan1", "speed", 10),
                    ("fan1", "dir", 0), ("fan1", "setpoint", 37)], sent
    FakeGLib.run_idles()
    assert svc[out + "setpoint/Dimming"] == 37                          # snapped value shown

    # Node never echoes: after the timeout the GUI falls back to the node's last report
    assert len(FakeGLib.timers) == 1
    FakeGLib.fire_timers()
    assert svc[out + "fan/State"] == 1 and svc[out + "fan/Status"] == 0x09
    assert svc[out + "speed/Dimming"] == 60 and svc[out + "setpoint/Dimming"] == 24

    # Node echoes: state follows
    svc.gui_write(out + "lid/State", 0)
    bridge.dispatch("maxxfan/fan1/state/lid", "0")
    FakeGLib.fire_timers()
    assert svc[out + "lid/State"] == 0 and svc[out + "lid/Status"] == 0x00

    # Broker lost: everything offline
    bridge._all_offline()
    assert svc["/Connected"] == 0 and svc["/State"] == 0
    assert svc[out + "fan/State"] == 1
    assert svc.gui_write(out + "fan/State", 0) is False

    assert d.snap(55, 10, 100, 10) in (50, 60) and d.snap(-9, -2, 37, 1) == -2

    # VanTurtle fan: no setpoint control, commands shown at once and handed to the worker
    import configparser
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    cfg.read_string("[fan2]\nname = Bed fan\nbackend = vanturtle\nrj45 = 0x27:2   ; RJ45\nrj11 = 0x26:2\n")
    FakeGLib.timers.clear()
    fan2, worker = d.make_vanturtle_fan("fan2", cfg, {}, None, 61, post=lambda fn, *a: fn(*a))
    worker.state_file = None
    svc2 = fan2.svc
    assert svc2["/DeviceInstance"] == 61 and svc2.name.endswith("maxxfan_fan2")
    assert not any("setpoint" in p for p in svc2.paths), "VanTurtle fans have no setpoint"
    assert (worker.rj45.address, worker.rj45.number, worker.rj11.address) == (0x27, 2, 0x26)
    assert (worker.rj45.reg_out, worker.rj45.reg_cfg, worker.rj45.reg_in) == (0x03, 0x07, 0x01)
    fan2.set_online(True)
    worker.belief["mode"] = 0
    assert svc2.gui_write(out + "speed/Dimming", 80) is True
    assert svc2.gui_write(out + "fan/State", 1) is True
    assert worker.desired["speed"] == 80 and worker.desired["on"] == 1
    FakeGLib.fire_timers()  # the echo timeout must not snap the GUI back mid-sequence
    assert svc2[out + "speed/Dimming"] == 80 and svc2[out + "fan/State"] == 1
    worker.report("mode", 1)  # what the worker posts when it senses auto mode
    assert svc2[out + "mode/Dimming"] == 1
    check_main_with_shipped_config(d)
    check_plugin_card_support(d)
    print("driver: all checks passed")


def check_main_with_shipped_config(d):
    """main() builds every card from the config that ships, without hardware: in a fresh data
    folder (as SetupHelper's /data/setupOptions/MaxxFanBridge) it first copies the defaults."""
    import shutil
    import tempfile
    sent, created, started = [], [], []
    client = types.SimpleNamespace(
        publish=lambda t, p, qos=1: sent.append((t, p)), subscribe=lambda topics: None,
        username_pw_set=lambda *a: None, reconnect_delay_set=lambda *a: None,
        connect_async=lambda *a, **k: sent.append(("CONNECT", a)), loop_start=lambda: None)

    class RecordingFan(d.Fan):
        def __init__(self, fan_id, *a, **k):
            created.append(fan_id)
            super().__init__(fan_id, *a, **k)

    import vanturtle
    saved = d.make_client, d.PrivateSystemBus, d.Fan, vanturtle.VanTurtleFan.start
    d.make_client, d.PrivateSystemBus, d.Fan = (lambda: client), (lambda: None), RecordingFan
    vanturtle.VanTurtleFan.start = lambda self: started.append(self.id)  # no threads in a test
    FakeGLib.MainLoop = lambda: types.SimpleNamespace(run=lambda: None)
    tmp_root = os.path.join(ROOT, ".build", "test-tmp")
    os.makedirs(tmp_root, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=tmp_root)
    data = os.path.join(tmp, "setupOptions", "MaxxFanBridge")
    try:
        assert d.main(["--data-dir", data]) == 0
        default = os.path.join(d.HERE, "config.default.ini")
        assert open(os.path.join(data, "config.ini")).read() == open(default).read()
        assert d.DATA_DIR == data
        # An edited config.ini is used as it is, never overwritten.
        with open(os.path.join(data, "config.ini"), "a") as f:
            f.write("\n[fan3]\nname = Achter\ninstance = 63\nbackend = vanturtle-wifi\n")
        created.clear()
        assert d.main(["--data-dir", data]) == 0
        assert created == ["fan1", "fan2", "fan3"], created
    finally:
        d.make_client, d.PrivateSystemBus, d.Fan, vanturtle.VanTurtleFan.start = saved
        d.DATA_DIR = d.HERE
        shutil.rmtree(tmp)
    assert created[:2] == ["fan1", "fan2"], created
    assert sent[0][0] == "CONNECT" and sent[0][1][0] == "127.0.0.1", sent
    assert d.VERSION == open(os.path.join(ROOT, "version")).read().strip().lstrip("v")
    check_dutch_cards(d)


def check_plugin_card_support(d):
    """What the gui-v2 plugin card (gui-plugin/) reads, and [gui] cards = plugin, which hides the
    switch-pane cards everywhere without losing what the user set for them."""
    import configparser
    out = "/SwitchableOutput/"
    fan = d.Fan("fan1", "Keuken", 60, lambda *a: None, bus=None, keys=d.VANTURTLE_KEYS, language="nl")
    assert fan.svc["/MaxxFan/Fan"] == 1, "how the plugin finds the fans"
    presets = d.Presets([("cooking", "Koken", {"fan1": None}), ("drive", "Rijden", {"fan1": None})],
                        {"fan1": fan}, None, language="nl")
    assert presets.svc["/MaxxFan/PresetKeys"] == ["cooking", "drive"], "config.ini order"
    assert presets.svc["/MaxxFan/CustomText"] == "Aangepast"
    assert "/MaxxFan/Fan" not in presets.svc.paths, "the presets card is not a fan"
    assert fan.svc[out + "speed/Settings/ShowUIControl"] == 1, "cards shown by default"

    def cards(value):
        cfg = configparser.ConfigParser()
        cfg.read_string("[gui]\ncards = %s\n" % value if value else "")
        return d.cards_hidden(cfg)
    assert cards(None) is False and cards("native") is False and cards(" Plugin ") is True
    try:
        cards("both")
        raise AssertionError("cards = both accepted")
    except ValueError as e:
        assert "native or plugin" in str(e)

    d.CARDS_HIDDEN = True
    try:
        hidden = d.Fan("fan2", "Bed", 61, lambda *a: None, bus=None, keys=d.VANTURTLE_KEYS)
        hidden_presets = d.Presets([("cooking", "Koken", {"fan2": None})], {"fan2": hidden}, None)
        for svc, keys in ((hidden.svc, d.VANTURTLE_KEYS), (hidden_presets.svc, ("cooking", "save"))):
            assert all(svc[out + k + "/Settings/ShowUIControl"] == 0 for k in keys), "hidden everywhere"
        assert hidden.svc.gui_write(out + "lid/Settings/ShowUIControl", 1) is False, "stays hidden"
        assert hidden.settings["lid_show"] == 1, "what the user chose is kept for cards = native"
        assert hidden.svc.gui_write(out + "lid/Settings/CustomName", "Klep") is True, "other edits work"
    finally:
        d.CARDS_HIDDEN = False


def check_dutch_cards(d):
    """[gui] language = nl: every text on the cards in Dutch; English stays the default."""
    import configparser
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    cfg.read_string("[gui]\nlanguage = nl\n[fan1]\nname = Keuken\nbackend = vanturtle-wifi\n")
    assert d.language(cfg) == "nl"
    fan, _worker = d.make_vtwifi_fan("fan1", cfg, None, 60, lambda *a: None)
    svc, out = fan.svc, "/SwitchableOutput/"
    assert svc["/CustomName"] == "Keuken" and svc[out + "fan/Settings/Group"] == "Keuken"
    names = {k: svc[out + k + "/Name"] for k in d.VANTURTLE_KEYS}
    assert names == {"fan": "Ventilator", "speed": "Snelheid", "direction": "Richting",
                     "lid": "Klep open", "mode": "Modus"}, names
    assert svc[out + "direction/Settings/Labels"] == ["Inblazen", "Afzuigen"]
    assert svc[out + "mode/Settings/Labels"] == ["Handmatig", "Automatisch"]
    presets = d.Presets([("cooking", "Koken", {"fan1": None})], {"fan1": fan}, None, language="nl")
    assert presets.svc["/CustomName"] == "Alle fans" and presets.svc[out + "save/Name"] == "Opslaan als"
    for t in d.TEXTS.values():  # every language has every text
        assert set(t) == set(d.TEXTS["en"])
    cfg.read_string("[gui]\nlanguage = fr\n")
    try:
        d.language(cfg)
        raise AssertionError("unknown language accepted")
    except ValueError:
        pass


if __name__ == "__main__":
    main()
