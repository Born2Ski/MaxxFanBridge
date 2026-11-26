"""Checks the project is a valid SetupHelper package (kwindrem/SetupHelper v9.x).

The rules come from SetupHelper's PackageManager.py and HelperResources:
  - the package name is the archive or repository name up to the first "-", so it may not
    contain one; PackageManager finds the package folder by its `version` file;
  - `version` is one line like v1.2 (v1.2~3, v1.2b3 for pre-releases);
  - `setup` is an executable bash script that sources IncludeHelpers and ends in endScript;
    endScript accepts INSTALL_SERVICES (the guidelines' "INSTALL_SERVICE" is ignored);
  - every folder in services/ becomes a daemontools service: run (and log/run) executable.
And our own: the service must start the driver from /data/<package> with its settings in
/data/setupOptions/<package>, and tools/make-package.sh must build an archive PackageManager
accepts from a USB stick.

    python3 tests/test_package.py
"""
import os
import re
import shutil
import subprocess
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "MaxxFanBridge"
TMP = os.path.join(ROOT, ".build", "test-tmp")  # stay inside the project folder
sys.path.insert(0, os.path.join(ROOT, "venus", "dbus-maxxfan-bridge"))
import forget  # noqa: E402


def read(*parts):
    with open(os.path.join(ROOT, *parts)) as f:
        return f.read()


def executable(*parts):
    return os.access(os.path.join(ROOT, *parts), os.X_OK)


def test_package_files():
    assert re.fullmatch(r"[A-Za-z0-9]+", NAME), "PackageManager splits names at the first -"
    assert re.fullmatch(r"v\d+\.\d+([~ab]\d+)?\n", read("version")), repr(read("version"))
    assert re.fullmatch(r"v\d+\.\d+\n", read("firstCompatibleVersion"))
    assert os.path.isfile(os.path.join(ROOT, "AUTO_INSTALL")), \
        "installs new versions without PackageManager's menus (classic UI only)"
    if os.path.exists(os.path.join(ROOT, "gitHubInfo")):  # only once the project is on GitHub
        info = read("gitHubInfo")
        assert re.fullmatch(r"[A-Za-z0-9-]+:[A-Za-z0-9._-]+\n", info), repr(info)
        assert "YOUR" not in info.upper(), "placeholder left in gitHubInfo"

    setup = read("setup")
    assert executable("setup") and setup.startswith("#!/bin/bash\n")
    assert 'source "/data/SetupHelper/HelperResources/IncludeHelpers"' in setup
    assert setup.rstrip().endswith("endScript INSTALL_SERVICES"), "endScript must be last"
    assert "INSTALL_SERVICE " not in setup + " ", "SetupHelper only knows INSTALL_SERVICES"
    assert "venus/dbus-maxxfan-bridge/config.default.ini" in setup
    if shutil.which("bash"):
        subprocess.run(["bash", "-n", os.path.join(ROOT, "setup")], check=True)


def test_setup_forgets_only_on_a_real_removal():
    """Removing the package forgets everything (owner's choice). SetupHelper also sets UNINSTALL
    to roll back a failed install; then nothing may be forgotten. Updates only install."""
    setup = read("setup")
    guarded = re.search(r"if \[ \"\$scriptAction\" == 'UNINSTALL' \] && ! \$installFailed ; then\n"
                        r"(.*?)\nfi\n", setup, re.S)
    assert guarded, "forget only when uninstalling and the install did not fail"
    assert "forget.py" in guarded.group(1) and setup.count("forget.py") == 1
    assert "svc -d /service/dbus-maxxfan-bridge" in guarded.group(1), "stop the driver first"
    assert guarded.start() < setup.index("endScript INSTALL_SERVICES"), "endScript never returns"


class FakeSettings:
    """com.victronenergy.settings /Settings/Devices: GetValue lists every setting below it."""

    def __init__(self, items):
        self.items, self.removed = dict(items), []

    def get_object(self, service, path):
        assert (service, path) == ("com.victronenergy.settings", "/Settings/Devices")
        return self

    def GetValue(self, dbus_interface):
        assert dbus_interface == "com.victronenergy.BusItem"
        return dict(self.items)

    def RemoveSettings(self, paths, dbus_interface):
        assert dbus_interface == "com.victronenergy.Settings"
        self.removed += paths
        for p in paths:
            del self.items[p]


def test_forget():
    bus = FakeSettings({
        "maxxfan_presets/CustomName": "Snelkeuze", "maxxfan_presets/cooking/Group": "Snelkeuze",
        "maxxfan_fan1/ClassAndVrmInstance": "switch:60", "maxxfan_fan2/lid/ShowUIControl": 1,
        "mppt_HQ1234/CustomName": "Dak", "maxxfanatic/x": 1, "tank_1/CustomName": "Water"})
    assert forget.remove_settings(bus) == [
        "maxxfan_fan1/ClassAndVrmInstance", "maxxfan_fan2/lid/ShowUIControl",
        "maxxfan_presets/CustomName", "maxxfan_presets/cooking/Group"]
    assert sorted(bus.items) == ["maxxfanatic/x", "mppt_HQ1234/CustomName", "tank_1/CustomName"], \
        "other devices' settings must stay"
    assert forget.remove_settings(bus) == [] and len(bus.removed) == 4, "nothing left to remove"

    folder = os.path.join(TMP, "forget", NAME)
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(os.path.join(folder, "paho", "mqtt"))
    for name in ("config.ini", "presets.json", "state-fan1.json", "state-fan2.json.tmp",
                 "DO_NOT_AUTO_INSTALL", "paho/mqtt/client.py"):
        open(os.path.join(folder, name), "w").close()
    assert forget.remove_files(folder) == ["config.ini", "presets.json", "state-fan1.json",
                                           "state-fan2.json.tmp"]
    left = sorted(os.path.relpath(os.path.join(d, f), folder) for d, _s, fs in os.walk(folder) for f in fs)
    assert left == ["DO_NOT_AUTO_INSTALL", "paho/mqtt/client.py"], \
        "SetupHelper's flags and a copied paho stay: " + repr(left)


def test_plugin_card():
    """The gui-v2 plugin: built from the QML that is here now, shipped, installed into /data/apps
    on install and removed again on every uninstall (also when a failed install is rolled back)."""
    import hashlib
    import json
    src = os.path.join(ROOT, "gui-plugin", "MaxxFanBridge")
    lines = sorted(read("gui-plugin", "MaxxFanBridge.sources").splitlines(), key=lambda l: l.split()[1])
    now = []
    for name in sorted(os.listdir(src)):
        with open(os.path.join(src, name), "rb") as f:
            now.append("%s  %s" % (hashlib.sha256(f.read()).hexdigest(), name))
    assert lines == now, "gui-plugin changed since the last build: run tools/make-plugin.sh"
    plugin = json.loads(read("gui-plugin", "MaxxFanBridge.json"))
    assert plugin["name"] == NAME and plugin["minRequiredVersion"] == "v1.4.6"
    assert plugin["version"] == read("version").strip().lstrip("v"), "rebuild with the new version"
    assert plugin["integrations"] == [{"type": 5, "url": "qrc:/MaxxFanBridge/MaxxFanBridge_Card.qml",
                                       "cardType": 2}], "one card, in the switch pane"
    setup = read("setup")
    install = re.search(r"if \[ \"\$scriptAction\" == 'INSTALL' \] && ! \$installFailed ; then\n"
                        r"    mkdir -p \"\$pluginDir/gui-v2\"(.*?)\nfi\n", setup, re.S)
    assert install and 'cp "$scriptDir/gui-plugin/MaxxFanBridge.json" "$pluginDir/gui-v2/' in install.group(1)
    assert "ln -sfn \"$pluginDir\" /data/apps/enabled/MaxxFanBridge" in install.group(1)
    assert 'pluginDir="/data/apps/available/MaxxFanBridge"' in setup
    removal = re.search(r"if \[ \"\$scriptAction\" == 'UNINSTALL' \]; then\n(.*?)\nfi\n", setup, re.S)
    assert removal and "rm -f /data/apps/enabled/MaxxFanBridge" in removal.group(1) \
        and 'rm -rf "$pluginDir"' in removal.group(1)
    assert removal.start() < setup.index("endScript INSTALL_SERVICES")


def test_service():
    services = os.listdir(os.path.join(ROOT, "services"))
    assert services == ["dbus-maxxfan-bridge"], services
    for run in (("run",), ("log", "run")):
        assert executable("services", "dbus-maxxfan-bridge", *run), run
    run = read("services", "dbus-maxxfan-bridge", "run")
    command = run.strip().splitlines()[-1].split()
    assert command[:2] == ["exec", "python3"], command
    script = command[2]
    prefix = "/data/%s/" % NAME
    assert script.startswith(prefix), script
    assert os.path.isfile(os.path.join(ROOT, script[len(prefix):])), "run starts a file the package has"
    assert executable(script[len(prefix):])
    assert command[3:] == ["--data-dir", "/data/setupOptions/%s" % NAME], command
    assert "multilog" in read("services", "dbus-maxxfan-bridge", "log", "run")


def test_archive_for_usb():
    """The archive PackageManager takes from a USB stick: name <package>-latest.tar.gz, one
    folder with a version file, executables kept, nothing for the desktop."""
    subprocess.run([os.path.join(ROOT, "tools", "make-package.sh"), "someone"], check=True,
                   stdout=subprocess.DEVNULL)
    path = os.path.join(ROOT, ".build", NAME + "-latest.tar.gz")
    assert os.path.basename(path).split("-", 1)[0] == NAME
    with tarfile.open(path) as tar:
        members = {m.name: m for m in tar.getmembers()}
        top = {n.split("/")[0] for n in members}
        assert top == {NAME + "-latest"}, top
        base = NAME + "-latest/"
        for must in ("version", "setup", "firstCompatibleVersion", "AUTO_INSTALL", "services/dbus-maxxfan-bridge/run",
                     "services/dbus-maxxfan-bridge/log/run", "venus/dbus-maxxfan-bridge/config.default.ini",
                     "venus/dbus-maxxfan-bridge/dbus-maxxfan-bridge.py", "venus/dbus-maxxfan-bridge/vtwifi.py",
                     "venus/dbus-maxxfan-bridge/forget.py", "gui-plugin/MaxxFanBridge.json"):
            assert base + must in members, must
        for exe in ("setup", "services/dbus-maxxfan-bridge/run", "services/dbus-maxxfan-bridge/log/run",
                    "venus/dbus-maxxfan-bridge/dbus-maxxfan-bridge.py"):
            assert members[base + exe].mode & 0o111, exe + " lost its executable bit"
        assert tar.extractfile(base + "gitHubInfo").read() == b"someone:latest\n"
        assert tar.extractfile(base + "version").read() == read("version").encode()
        unwanted = [n for n in members if "/tests/" in n or "/archive/" in n or "__pycache__" in n
                    or "/._" in n or n.endswith(".DS_Store") or n.endswith("/config.ini")]
        assert not unwanted, unwanted
        assert all(m.uid == 0 for m in members.values()), "files should belong to root"


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
    print("package: all %d checks passed" % len(tests))


if __name__ == "__main__":
    sys.exit(main())
