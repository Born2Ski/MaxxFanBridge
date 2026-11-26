#!/usr/bin/env python3
"""Forget everything MaxxFanBridge kept on this Venus device, so a reinstall starts like new.

The setup script runs this when the package is really removed (not when a failed install is
rolled back, and never on an update):

  - the settings Venus OS keeps for our cards, everything under /Settings/Devices/maxxfan_*:
    card titles, grouping, hidden controls, control types, device instances;
  - in the settings folder: config.ini, presets.json and the lid memory (state-*.json).

A paho-mqtt copied into the settings folder stays (a reinstall needs it on a Venus OS without
it), and so do SetupHelper's own flags there.

    python3 forget.py /data/setupOptions/MaxxFanBridge
"""
import glob
import os
import sys

SETTINGS = "com.victronenergy.settings"
DEVICES = "/Settings/Devices"
PREFIX = "maxxfan_"  # the driver's services are com.victronenergy.switch.maxxfan_<id>
FILES = ("config.ini", "presets.json", "state-*.json", "*.tmp")


def ours(items):
    """Paths below /Settings/Devices that belong to our cards, relative to it."""
    return sorted(str(p) for p in items if str(p).startswith(PREFIX))


def remove_settings(bus):
    devices = bus.get_object(SETTINGS, DEVICES)
    paths = ours(devices.GetValue(dbus_interface="com.victronenergy.BusItem"))
    if paths:
        devices.RemoveSettings(paths, dbus_interface="com.victronenergy.Settings")
    return paths


def remove_files(data_dir):
    removed = []
    for pattern in FILES:
        for path in sorted(glob.glob(os.path.join(data_dir, pattern))):
            if os.path.isfile(path):
                os.remove(path)
                removed.append(os.path.basename(path))
    return removed


def main(argv):
    if len(argv) != 2:
        print("usage: forget.py <settings folder>", file=sys.stderr)
        return 2
    status = 0
    try:
        import dbus
        paths = remove_settings(dbus.SystemBus())
        print("forgot %d Venus OS settings of the MaxxFan cards" % len(paths))
    except Exception as e:  # keep going: the files can still go
        print("could not remove the Venus OS settings of the MaxxFan cards: %s" % e)
        status = 1
    files = remove_files(argv[1])
    print("removed from %s: %s" % (argv[1], ", ".join(files) or "nothing"))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv))
