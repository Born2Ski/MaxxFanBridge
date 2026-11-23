"""Desktop test of the presets card (Cooking, Sleep, Drive, Standard) with stand-in fans.

    python3 tests/test_presets.py
"""
import configparser
import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from test_driver import FakeGLib, load_driver  # noqa: E402

TMP = os.path.join(ROOT, ".build", "test-tmp")
CONFIG = os.path.join(ROOT, "venus", "dbus-maxxfan-bridge", "config.default.ini")
OUT = "/SwitchableOutput/"
d = load_driver()


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def shipped_config():
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    cfg.read(CONFIG)
    return cfg


def make_fans():
    sent = []
    fans = {}
    for fan_id, name, instance in (("fan1", "Galley fan", 60), ("fan2", "Bed fan", 61)):
        fan = d.Fan(fan_id, name, instance, lambda *a: sent.append(a), bus=None, keys=d.VANTURTLE_KEYS)
        fan.set_online(True)
        fans[fan_id] = fan
    return fans, sent


def show(card, **values):
    for key, value in values.items():
        dim = d.BY_KEY[key][5]
        card.svc[OUT + key + ("/Dimming" if dim else "/State")] = value


def lit(presets):
    return [k for k in presets.order if presets.svc[OUT + k + "/State"] == 1]


def test_parse_and_format():
    p = d.parse_target
    assert p("exhaust 80") == {"mode": 0, "fan": 1, "direction": 1, "speed": 80, "lid": 1}
    assert p("Intake 30% open") == {"mode": 0, "fan": 1, "direction": 0, "speed": 30, "lid": 1}
    assert p("off") == {"mode": 0, "fan": 0} and p("off open")["lid"] == 1 and p("off closed")["lid"] == 0
    assert p("auto") == {"mode": 1} and p("keep") is None
    for bad in ("", "exhaust", "exhaust 85", "exhaust 0", "fast 50", "off ajar", "auto 50", "intake 30 open now",
                "intake 30 closed"):  # a closed lid means the fan is off
        try:
            p(bad)
        except ValueError:
            continue
        raise AssertionError("accepted %r" % bad)
    for text in ("exhaust 80 open", "intake 30 open", "off open", "off closed", "off", "auto"):
        assert d.format_target(p(text)) == text, text
    assert d.format_target({"mode": 0, "fan": 1, "direction": 0, "speed": 50, "lid": 1}) == "intake 50 open"


def test_shipped_config():
    presets = d.read_presets(shipped_config(), ["fan1", "fan2"])
    assert [(k, label) for k, label, _t in presets] == [
        ("cooking", "Koken"), ("sleep", "Slapen"), ("drive", "Rijden"), ("standard", "Standaard")]
    t = {k: targets for k, _l, targets in presets}
    assert t["cooking"]["fan1"]["direction"] == 1 and t["cooking"]["fan1"]["speed"] == 80
    assert t["sleep"]["fan2"] == {"mode": 0, "fan": 0, "lid": 1}
    assert t["drive"]["fan1"] == t["drive"]["fan2"] == {"mode": 0, "fan": 0, "lid": 0}
    # Fans the driver skips are not presets, and the presets section is not a fan.
    cfg = shipped_config()
    fans = [s for s in cfg.sections() if s not in ("mqtt", "presets", "gui") and not s.startswith("preset ")]
    assert fans == ["fan1", "fan2"]


def test_config_errors():
    for text, needle in (("[preset x]\nfan3 = off\n", "no fan called fan3"),
                         ("[preset x]\nfan1 = sideways 20\n", "fan1"),
                         ("[preset bad name!]\nfan1 = off\n", "letters"),
                         ("[preset save]\nfan1 = off\n", "letters")):
        cfg = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
        cfg.read_string(text)
        try:
            d.read_presets(cfg, ["fan1", "fan2"])
        except ValueError as e:
            assert needle in str(e), (text, e)
            continue
        raise AssertionError("accepted " + text)
    cfg = configparser.ConfigParser()
    cfg.read_string("[preset quiet]\nfan1 = exhaust 20\n")
    (key, label, targets), = d.read_presets(cfg, ["fan1", "fan2"])
    assert (key, label, targets["fan2"]) == ("quiet", "Quiet", None), "missing fan means keep"


def test_closing_the_lid_stops_the_fan():
    """Klep dicht: the fan is switched off first. Klep open: nothing else starts."""
    fans, sent = make_fans()
    fan = fans["fan1"]
    show(fan, fan=1, speed=60, direction=1, lid=1, mode=0)
    assert fan.svc.gui_write(OUT + "lid/State", 0) is True
    assert sent == [("fan1", "on", 0), ("fan1", "lid", 0)], "off first, then the lid"
    assert fan.svc[OUT + "fan/State"] == 0 and fan.svc[OUT + "lid/State"] == 0
    sent.clear()
    assert fan.svc.gui_write(OUT + "lid/State", 1) is True
    assert sent == [("fan1", "lid", 1)] and fan.svc[OUT + "fan/State"] == 0, "opening starts nothing"
    sent.clear()
    show(fan, fan=0)  # the card may be wrong about the fan (keypad): off is sent anyway
    assert fan.command("lid", 0) is True
    assert sent == [("fan1", "on", 0), ("fan1", "lid", 0)], sent
    sent.clear()
    assert fan.command("fan", 0) and fan.command("lid", 0)  # a preset's "off closed": off once
    assert sent == [("fan1", "on", 0), ("fan1", "lid", 0)], sent
    sent.clear()
    fan.command("fan", 0)
    show(fan, fan=1)  # then started from the keypad, as the card now shows
    fan.command("lid", 0)
    assert sent == [("fan1", "on", 0), ("fan1", "on", 0), ("fan1", "lid", 0)], "running: off again"
    sent.clear()
    show(fan, fan=1, lid=1)
    assert fan.svc.gui_write(OUT + "fan/State", 0) is True
    assert sent == [("fan1", "on", 0)] and fan.svc[OUT + "lid/State"] == 1, "switching off leaves the lid"


def test_card_and_apply():
    fans, sent = make_fans()
    clock = Clock()
    presets = d.Presets(d.read_presets(shipped_config(), list(fans)), fans, None, 62, clock=clock)
    svc = presets.svc
    assert svc.name == "com.victronenergy.switch.maxxfan_presets" and svc.registered
    assert svc["/DeviceInstance"] == 62 and svc["/Connected"] == 1 and svc["/State"] == 0x100
    assert svc[OUT + "cooking/Name"] == "Koken" and svc[OUT + "cooking/Settings/Type"] == 1
    assert svc[OUT + "save/Settings/Labels"] == ["—", "Koken", "Slapen", "Rijden", "Standaard"]
    assert svc[OUT + "save/Name"] == "Save as", "English unless told otherwise"
    assert svc[OUT + "save/Settings/Type"] == 6 and svc[OUT + "cooking/Settings/Group"] == "Fan presets"
    assert svc.gui_write(OUT + "sleep/Settings/CustomName", "Night") is True
    assert presets.settings["sleep_name"] == "Night"

    # Fans as they are: fan1 exhaust 60 running, fan2 off and closed, neither in Auto.
    show(fans["fan1"], fan=1, speed=60, direction=1, lid=1, mode=0)
    show(fans["fan2"], fan=0, speed=20, direction=0, lid=0, mode=0)
    assert svc.gui_write(OUT + "cooking/State", 1) is True
    assert sent == [("fan1", "on", 1), ("fan1", "lid", 1), ("fan1", "dir", 1), ("fan1", "speed", 80),
                    ("fan2", "on", 1), ("fan2", "lid", 1), ("fan2", "dir", 0), ("fan2", "speed", 30)], sent
    assert fans["fan2"].snapshot() == {"fan": 1, "speed": 30, "direction": 0, "lid": 1, "mode": 0}
    assert lit(presets) == ["cooking"]

    # Another preset: the first goes dark. Drive closes both lids.
    del sent[:]
    assert svc.gui_write(OUT + "drive/State", 1) is True
    assert lit(presets) == ["drive"]
    assert sent == [("fan1", "on", 0), ("fan1", "lid", 0), ("fan2", "on", 0), ("fan2", "lid", 0)], sent

    # Touching a fan's control on its card darkens the preset; nothing else is sent.
    del sent[:]
    assert fans["fan1"].svc.gui_write(OUT + "speed/Dimming", 40) is True
    assert lit(presets) == [] and sent == [("fan1", "speed", 40)]

    # Switching a lit preset off only darkens it.
    svc.gui_write(OUT + "standard/State", 1)
    del sent[:]
    assert svc.gui_write(OUT + "standard/State", 0) is True
    assert lit(presets) == [] and sent == []


def test_auto_and_offline():
    fans, sent = make_fans()
    cfg = configparser.ConfigParser()
    cfg.read_string("[preset thermo]\nfan1 = auto\nfan2 = keep\n[preset std]\nfan1 = exhaust 40\nfan2 = intake 40\n")
    presets = d.Presets(d.read_presets(cfg, list(fans)), fans, None, 62, clock=Clock())
    show(fans["fan1"], fan=1, speed=60, direction=1, lid=1, mode=1)
    show(fans["fan2"], fan=0, speed=20, direction=0, lid=0, mode=0)
    presets.svc.gui_write(OUT + "std/State", 1)
    assert sent[0] == ("fan1", "mode", 0), "leave Auto before the manual values"
    assert ("fan2", "mode", 0) not in sent, "fan 2 was not in Auto"
    del sent[:]
    presets.svc.gui_write(OUT + "thermo/State", 1)
    assert sent == [("fan1", "mode", 1)], "auto only switches the thermostat on; keep leaves fan 2 alone"
    # Touching the kept fan does not darken a preset that leaves it alone.
    fans["fan2"].svc.gui_write(OUT + "speed/Dimming", 70)
    assert lit(presets) == ["thermo"]

    del sent[:]
    fans["fan2"].set_online(False)
    presets.svc.gui_write(OUT + "std/State", 1)
    assert sent and all(f == "fan1" for f, _k, _v in sent), "offline fan left alone"
    fans["fan1"].set_online(False)
    assert presets.svc.gui_write(OUT + "thermo/State", 1) is False, "nothing reachable: refused"
    assert lit(presets) == ["std"], "a refused tap changes nothing"


def test_drift_darkens_after_a_minute():
    fans, _sent = make_fans()
    clock = Clock()
    presets = d.Presets(d.read_presets(shipped_config(), list(fans)), fans, None, 62, clock=clock)
    presets.svc.gui_write(OUT + "standard/State", 1)
    clock.t += 30
    show(fans["fan2"], speed=90)  # someone used the keypad
    presets.tick()
    assert lit(presets) == ["standard"], "fans may still be getting there"
    clock.t += 31
    presets.tick()
    assert lit(presets) == []
    presets.svc.gui_write(OUT + "standard/State", 1)
    clock.t += 120
    presets.tick()
    assert lit(presets) == ["standard"], "still matching: stays lit"


def test_save_as():
    os.makedirs(TMP, exist_ok=True)
    store = os.path.join(TMP, "presets.json")
    if os.path.exists(store):
        os.remove(store)
    fans, sent = make_fans()
    presets = d.Presets(d.read_presets(shipped_config(), list(fans)), fans, None, 62, store=store, clock=Clock())
    show(fans["fan1"], fan=1, speed=30, direction=0, lid=1, mode=0)
    show(fans["fan2"], fan=0, speed=20, direction=0, lid=1, mode=0)
    FakeGLib.idles.clear()
    assert presets.svc.gui_write(OUT + "save/Dimming", 2) is True  # "Sleep"
    FakeGLib.run_idles()
    assert presets.svc[OUT + "save/Dimming"] == 0, "menu goes back to —"
    assert lit(presets) == ["sleep"] and sent == [], "saving sends nothing"
    with open(store) as f:
        saved = json.load(f)
    assert saved == {"sleep": {"fan1": "intake 30 open", "fan2": "off open"}}, saved

    # After a restart the saved Sleep wins over config.ini; the others still follow config.ini.
    fans2, sent2 = make_fans()
    again = d.Presets(d.read_presets(shipped_config(), list(fans2)), fans2, None, 62, store=store, clock=Clock())
    assert again.texts("sleep") == {"fan1": "intake 30 open", "fan2": "off open"}
    assert again.texts("cooking") == {"fan1": "exhaust 80 open", "fan2": "intake 30 open"}
    show(fans2["fan1"], fan=0, lid=0)
    again.svc.gui_write(OUT + "sleep/State", 1)
    assert sent2[:4] == [("fan1", "on", 1), ("fan1", "lid", 1), ("fan1", "dir", 0), ("fan1", "speed", 30)]

    # An offline fan keeps its old value in the saved preset.
    fans["fan2"].set_online(False)
    show(fans["fan1"], fan=1, speed=50, direction=1, lid=1)
    presets.svc.gui_write(OUT + "save/Dimming", 4)  # "Standard"
    assert presets.texts("standard") == {"fan1": "exhaust 50 open", "fan2": "intake 40 open"}
    # A damaged file is ignored, not fatal.
    with open(store, "w") as f:
        f.write("{not json")
    d.Presets(d.read_presets(shipped_config(), list(fans2)), fans2, None, 62, store=store, clock=Clock())


def test_with_vanturtle_wifi_backend():
    """A preset tap ends up as the VanTurtle controller's MQTT commands, one at a time."""
    clock = Clock()
    published = []
    cfg = configparser.ConfigParser()
    cfg.read_string("[fan1]\nbackend = vanturtle-wifi\n[fan2]\nbackend = vanturtle-wifi\n")
    fans, workers = {}, {}
    for fan_id, instance in (("fan1", 60), ("fan2", 61)):
        fan, worker = d.make_vtwifi_fan(fan_id, cfg, None, instance,
                                        lambda t, p: published.append((t, p)), clock=clock)
        worker.state_file = None
        fans[fan_id], workers[fan_id] = fan, worker
        for leaf, value in (("on", "0"), ("speed", "2"), ("dir", "0"), ("auto", "0")):
            worker.on_message(leaf, value, True)
        worker.on_message("alive", "1")
        worker.lid = 0
    presets = d.Presets(d.read_presets(shipped_config(), list(fans)), fans, None, 62, clock=clock)
    clock.t += 5
    assert presets.svc.gui_write(OUT + "cooking/State", 1) is True
    assert published == [("maxxfan/fan1/vt/on", "1"), ("maxxfan/fan2/vt/on", "1")], "one per controller"
    assert workers["fan1"].wish == {"on": 1, "lid": 1, "dir": 1, "speed": 80}
    assert fans["fan1"].snapshot() == {"fan": 1, "speed": 80, "direction": 1, "lid": 1, "mode": 0}
    # The controllers confirm; the rest follows in order after the quiet gap.
    for fan_id in ("fan1", "fan2"):
        workers[fan_id].on_message("on", "1")  # echo
        workers[fan_id].on_message("on", "1")  # confirmation
    for _ in range(20):  # on_opens_lid unknown: the lid waits a full stroke after switching on
        clock.t += 1
        for w in workers.values():
            w.tick()
    topics = [t for t, _p in published]
    assert topics.index("maxxfan/fan1/vt/lid") > topics.index("maxxfan/fan1/vt/on")
    assert lit(presets) == ["cooking"]


def main():
    for name, test in sorted(globals().items()):
        if name.startswith("test_"):
            test()
    print("presets: all checks passed")


if __name__ == "__main__":
    main()
