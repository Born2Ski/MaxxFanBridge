"""Desktop test of the gui-v2 plugin card (gui-plugin/MaxxFanBridge) against the real driver.

gui-v2 itself cannot run here. The plugin's QML runs in Qt 6 (PySide6), offscreen, with
stand-ins for the Victron.GuiPlugins types (tests/plugin_stubs) that follow gui-v2's documented
behaviour (.github/gui-plugins.md at v1.4.6). Their data comes from the driver's own services
(the stand-in D-Bus of test_driver), so a tap on the card goes through the driver exactly as a
touch on a switch-pane card does. It also saves screenshots in .build/test-tmp/plugin-*.png.

    python3 tests/test_plugin.py

Needs PySide6. Without it, the test uses .build/qtvenv (tools/make-plugin.sh sets that up), or
says it is skipped.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PYTHON = os.path.join(ROOT, ".build", "qtvenv", "bin", "python")
# mutation_check.py points this at a copy of the plugin with a planted bug.
PLUGIN = os.environ.get("MAXXFAN_PLUGIN_DIR", os.path.join(ROOT, "gui-plugin", "MaxxFanBridge"))
STUBS = os.path.join(ROOT, "tests", "plugin_stubs")
sys.path.insert(0, os.path.join(ROOT, "tests"))
import plugin_api  # noqa: E402

plugin_api.check_api_use(PLUGIN)

try:
    import PySide6  # noqa: F401
except ImportError:
    if os.path.exists(VENV_PYTHON) and os.path.realpath(sys.prefix) != os.path.realpath(os.path.dirname(os.path.dirname(VENV_PYTHON))):
        os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)
    print("plugin: API check passed; the rest skipped (no PySide6; run tools/make-plugin.sh once to set it up)")
    sys.exit(0)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QMetaObject, QObject, QPointF, Qt, QUrl, Signal, Slot  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQuick import QQuickItem, QQuickView, QQuickWindow, QSGRendererInterface  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "tests"))
import test_presets as tp  # noqa: E402

d = tp.d
SHOTS = os.path.join(ROOT, ".build", "test-tmp")
OUT = "/SwitchableOutput/"


def plain(value):
    """A JavaScript value from QML as plain Python (lists, dicts, numbers, text)."""
    return value.toVariant() if hasattr(value, "toVariant") else value


class FakeBus(QObject):
    """What a PluginDataItem and a PluginDeviceModel see: the driver's services, by uid
    ("dbus/<service name><path>"). Writes go through the service as gui-v2's do."""

    changed = Signal(str)
    devicesChanged = Signal()

    def __init__(self, services):
        super().__init__()
        self.services = {"dbus/" + svc.name: svc for svc in services}
        self.writes, self.pages, self.seen = [], [], set()

    def _find(self, uid):
        for base, svc in self.services.items():
            if uid.startswith(base + "/") and uid[len(base):] in svc.paths:
                return svc, uid[len(base):]
        return None, None

    @Slot(str, result=bool)
    def has(self, uid):
        self.seen.add(uid)
        svc, path = self._find(uid)
        return svc is not None and svc.paths[path] is not None

    @Slot(str, result="QVariant")
    def value(self, uid):
        svc, path = self._find(uid)
        return svc.paths[path] if svc else None

    @Slot(str, "QVariant")
    def write(self, uid, value):
        svc, path = self._find(uid)
        value = plain(value)
        accepted = svc.gui_write(path, value) if svc else False
        self.writes.append((uid, value, accepted))
        self.refresh()

    @Slot("QVariant", "QVariant", result="QVariant")
    def devices(self, service_types, required_paths):
        found = []
        service_types, required_paths = plain(service_types), plain(required_paths)
        for base, svc in self.services.items():
            service_type = svc.name.split(".")[2]
            if service_types and service_type not in service_types:
                continue
            if all(self.has(base + "/" + p.lstrip("/")) for p in required_paths or []):
                found.append({"serviceUid": base, "serviceType": service_type,
                              "deviceInstance": svc.paths["/DeviceInstance"], "name": svc.paths["/CustomName"]})
        return sorted(found, key=lambda device: device["name"])

    @Slot(str, "QVariant", str)
    def pushPage(self, url, properties, text):
        self.pages.append((os.path.basename(url), dict(plain(properties)), text))

    def refresh(self):
        """After the driver changed something: every value a data item has asked for again."""
        for uid in sorted(self.seen):
            self.changed.emit(uid)


def make_system():
    """Keuken (fan1) exhausting at 80 %, Bed (fan2) off and closed; the shipped presets; Dutch."""
    sent = []
    fans = {}
    for fan_id, name, instance in (("fan1", "Keuken", 60), ("fan2", "Bed", 61)):
        fan = d.Fan(fan_id, name, instance, lambda *a: sent.append(a), bus=None, keys=d.VANTURTLE_KEYS,
                    language="nl")
        fan.set_online(True)
        fans[fan_id] = fan
    tp.show(fans["fan1"], fan=1, speed=80, direction=1, lid=1, mode=0)
    tp.show(fans["fan2"], fan=0, speed=30, direction=0, lid=0, mode=0)
    cfg = tp.shipped_config()
    presets = d.Presets(d.read_presets(cfg, list(fans)), fans, None, 62, cfg.get("presets", "name"),
                        clock=tp.Clock(), language="nl")
    bus = FakeBus([fans["fan1"].svc, fans["fan2"].svc, presets.svc])
    return fans, presets, bus, sent


def load(bus, qml, properties=None):
    view = QQuickView()
    view.engine().addImportPath(STUBS)
    view.rootContext().setContextProperty("fakeBus", bus)
    if properties:
        view.setInitialProperties(properties)
    view.setSource(QUrl.fromLocalFile(os.path.join(PLUGIN, qml)))
    errors = [e.toString() for e in view.errors()]
    assert view.status() == QQuickView.Ready and not errors, errors
    view.resize(view.rootObject().width(), view.rootObject().height())
    view.show()
    QTest.qWait(50)
    return view


def item(view, name):
    """An item by objectName, searched in the visual tree (a Repeater's items are only there)."""
    todo = [view.rootObject()]
    while todo:
        it = todo.pop(0)
        if it.objectName() == name:
            return it
        todo += it.childItems()
    raise AssertionError("no item " + name)


def tap(view, it):
    centre = it.mapToScene(QPointF(it.width() / 2, it.height() / 2)).toPoint()
    QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, centre)
    QTest.qWait(20)


def lit_tiles(view):
    return [n for n in ("cooking", "sleep", "drive", "standard", "custom")
            if item(view, "tile_" + n).property("lit")]


def screenshot(view, name):
    os.makedirs(SHOTS, exist_ok=True)
    view.grabWindow().save(os.path.join(SHOTS, "plugin-%s.png" % name))


def list_rows(view):
    """The list items of a page, in order, with what they show."""
    listview = view.rootObject().childItems()[0]
    return [row for row in listview.childItems() if row.property("visible")]


def test_card(app):
    fans, presets, bus, sent = make_system()
    view = load(bus, "MaxxFanBridge_Card.qml")
    root = view.rootObject()
    assert root.property("title") == "Alle fans"
    assert root.property("status") == "Aangepast", "no preset on: Aangepast"
    labels = [item(view, "tile_" + k).property("label") for k in ("cooking", "sleep", "drive", "standard", "custom")]
    assert labels == ["Koken", "Slapen", "Rijden", "Standaard", "Aangepast"], labels
    assert lit_tiles(view) == ["custom"]
    rows = [(item(view, n).property("text"), item(view, n).property("secondaryText")) for n in ("fanRow0", "fanRow1")]
    assert rows == [("Bed", "Uit"), ("Keuken", "Afzuigen 80 %")], rows
    screenshot(view, "card-aangepast")

    # Tapping Koken switches that preset on through the driver: the fans get their commands.
    tap(view, item(view, "tile_cooking"))
    assert bus.writes == [("dbus/com.victronenergy.switch.maxxfan_presets/SwitchableOutput/cooking/State", 1, True)]
    assert ("fan2", "on", 1) in sent and ("fan1", "speed", 80) in sent
    assert root.property("status") == "Koken" and lit_tiles(view) == ["cooking"]
    assert item(view, "fanRow0").property("secondaryText") == "Inblazen 30 %"
    screenshot(view, "card-koken")

    # A touch on a fan (here from its own card or page) puts the card back on Aangepast.
    fans["fan2"].svc.gui_write(OUT + "speed/Dimming", 50)
    bus.refresh()
    assert root.property("status") == "Aangepast" and lit_tiles(view) == ["custom"]

    # Aangepast opens both fans; a fan's row opens that fan.
    del bus.pages[:]
    tap(view, item(view, "tile_custom"))
    assert bus.pages == [("MaxxFanBridge_AllFans.qml", {
        "title": "Alle fans", "uid1": "dbus/com.victronenergy.switch.maxxfan_fan2", "name1": "Bed",
        "uid2": "dbus/com.victronenergy.switch.maxxfan_fan1", "name2": "Keuken"}, "Aangepast")], bus.pages
    tap(view, item(view, "fanRow1"))
    assert bus.pages[-1] == ("MaxxFanBridge_Fan.qml", {"serviceUid": "dbus/com.victronenergy.switch.maxxfan_fan1",
                                                       "title": "Keuken"}, "Keuken"), bus.pages[-1]

    # Auto shows as such; a fan that is not connected shows a dash.
    tp.show(fans["fan1"], mode=1)
    fans["fan2"].set_online(False)
    bus.refresh()
    rows = [item(view, n).property("secondaryText") for n in ("fanRow0", "fanRow1")]
    assert rows == ["—", "Automatisch"], rows

    # No fan connected: the driver would refuse a preset, so the icons are greyed out.
    fans["fan1"].set_online(False)
    bus.refresh()
    assert not item(view, "tile_sleep").property("enabled") and item(view, "tile_custom").property("enabled")
    del bus.writes[:]
    tap(view, item(view, "tile_sleep"))
    assert bus.writes == [], "greyed out: nothing written"
    screenshot(view, "card-offline")


def test_names_follow_the_switch_pane(app):
    """A preset or a control renamed in the switch pane's edit mode is renamed here too."""
    fans, presets, bus, _sent = make_system()
    presets.svc.gui_write(OUT + "sleep/Settings/CustomName", "Nacht")
    view = load(bus, "MaxxFanBridge_Card.qml")
    assert item(view, "tile_sleep").property("label") == "Nacht"
    fans["fan1"].svc.gui_write(OUT + "lid/Settings/CustomName", "Dakluik")
    page = load(bus, "MaxxFanBridge_Fan.qml", {"serviceUid": "dbus/com.victronenergy.switch.maxxfan_fan1"})
    assert [r.property("text") for r in list_rows(page)][3] == "Dakluik"


def test_fan_page(app):
    fans, presets, bus, sent = make_system()
    view = load(bus, "MaxxFanBridge_Fan.qml", {"serviceUid": "dbus/com.victronenergy.switch.maxxfan_fan1"})
    rows = list_rows(view)
    assert [(r.property("text"), r.property("secondaryText")) for r in rows] == [
        ("Ventilator", "Aan"), ("Snelheid", "80"), ("Richting", "Afzuigen"), ("Klep open", "Aan"),
        ("Modus", "Handmatig")], [(r.property("text"), r.property("secondaryText")) for r in rows]
    assert plain(rows[2].property("optionModel")) == [{"display": "Inblazen", "value": 0},
                                                      {"display": "Afzuigen", "value": 1}]
    screenshot(view, "fan-keuken")

    # The controls write what a touch on the switch-pane card would; the driver acts on it.
    del sent[:]
    QMetaObject.invokeMethod(rows[4], "pick", Q_ARG_INT(1))
    QMetaObject.invokeMethod(rows[1], "move", Q_ARG_REAL(60))
    QMetaObject.invokeMethod(rows[3], "click")
    assert sent == [("fan1", "mode", 1), ("fan1", "speed", 60), ("fan1", "on", 0), ("fan1", "lid", 0)], \
        "Auto, 60 %, and closing the lid switches the fan off first: %r" % sent

    # Not connected: the controls are greyed out and write nothing.
    fans["fan1"].set_online(False)
    bus.refresh()
    assert not any(r.property("interactive") for r in rows)
    del bus.writes[:]
    QMetaObject.invokeMethod(rows[0], "click")
    assert bus.writes == []


def test_all_fans_page(app):
    fans, presets, bus, sent = make_system()
    view = load(bus, "MaxxFanBridge_AllFans.qml", {
        "title": "Alle fans", "uid1": "dbus/com.victronenergy.switch.maxxfan_fan2", "name1": "Bed",
        "uid2": "dbus/com.victronenergy.switch.maxxfan_fan1", "name2": "Keuken"})
    texts = [r.property("text") for r in list_rows(view)]
    assert texts == ["Bed", "Ventilator", "Snelheid", "Richting", "Klep open", "Modus",
                     "Keuken", "Ventilator", "Snelheid", "Richting", "Klep open", "Modus"], texts
    rows = list_rows(view)
    del sent[:]
    QMetaObject.invokeMethod(rows[1], "click")  # Bed's Ventilator
    QMetaObject.invokeMethod(rows[8], "move", Q_ARG_REAL(40))  # Keuken's Snelheid
    assert sent == [("fan2", "on", 1), ("fan1", "speed", 40)], sent
    view.resize(800, 720)
    screenshot(view, "all-fans")


def Q_ARG_INT(value):
    from PySide6.QtCore import Q_ARG
    return Q_ARG("QVariant", value)


def Q_ARG_REAL(value):
    from PySide6.QtCore import Q_ARG
    return Q_ARG("QVariant", value)


def main():
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test(app)
    print("plugin: API check and %d checks passed (screenshots in .build/test-tmp/plugin-*.png)" % len(tests))


if __name__ == "__main__":
    sys.exit(main())
