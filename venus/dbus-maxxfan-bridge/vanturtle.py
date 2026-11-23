"""VanTurtle MaxxFan controller board, driven over the Venus device's own I2C bus (option V)
or through an ESP32 at the fan (option E: the channels come from vtboard.py instead).

The board shorts the pin pairs of the MaxxFan wall-control jacks, so every command is a
key press. The fan reports nothing back except whether auto mode is on. This module keeps
a *belief* of the fan's state and presses keys until the belief matches the *desired*
state. RJ11 keys (Off, Open, Close) are absolute and repair the belief; RJ45 keys are
toggles and steps that trust it. Register map and timing: vanturtle.com/vtafc-docs.
"""

import fcntl
import json
import logging
import os
import threading
import time

log = logging.getLogger("dbus-maxxfan-bridge")

I2C_SLAVE = 0x0703

LED = 0x02  # activity LED on the VanTurtle board, lit during each press
# RJ45 port (toggles and steps)
AUTO, INOUT, ONOFF, FASTER, SLOWER, BEEP = 0x04, 0x08, 0x10, 0x20, 0x40, 0x80
LID_TOGGLE = FASTER | SLOWER  # both together: open/close toggle on the 7000K / 7500K
# RJ11 port (absolute)
RJ11_ON, RJ11_CLOSE, RJ11_OPEN, RJ11_OFF = 0x08, 0x10, 0x20, 0x40

KEYS = ("on", "speed", "dir", "lid", "mode")


class I2CBus:
    """/dev/i2c-N with plain ioctl, so nothing beyond the Python standard library is needed."""

    def __init__(self, number):
        self.number = number
        self.fd = None
        self.lock = threading.Lock()

    def _select(self, address):
        if self.fd is None:
            self.fd = os.open("/dev/i2c-%d" % self.number, os.O_RDWR)
        fcntl.ioctl(self.fd, I2C_SLAVE, address)

    def write(self, address, reg, value):
        with self.lock:
            self._select(address)
            os.write(self.fd, bytes((reg, value)))

    def read(self, address, reg):
        with self.lock:
            self._select(address)
            os.write(self.fd, bytes((reg,)))
            return os.read(self.fd, 1)[0]

    def reset(self):
        with self.lock:
            if self.fd is not None:
                try:
                    os.close(self.fd)
                except OSError:
                    pass
                self.fd = None


def parse_channel(text):
    """'0x27:1' -> (0x27, 1): board address and channel (1 or 2) on that board."""
    address, _, channel = text.partition(":")
    address, channel = int(address, 0), int(channel or "1")
    if not 0x20 <= address <= 0x27 or channel not in (1, 2):
        raise ValueError("bad VanTurtle channel %r, expected e.g. 0x27:1" % text)
    return address, channel


class Channel:
    """One fan port of a VanTurtle board: an 8-bit port of its I/O expander."""

    def __init__(self, bus, address, number):
        i = number - 1
        self.bus, self.address, self.number = bus, address, number
        self.reg_in, self.reg_out, self.reg_cfg = 0x00 + i, 0x02 + i, 0x06 + i

    def __repr__(self):
        return "0x%02x:%d" % (self.address, self.number)

    def init(self):
        # Outputs first: expanders of this family power up with their output latches high,
        # so making the pins outputs first would press every key at once. Also releases a
        # key left held by a crash.
        self.bus.write(self.address, self.reg_out, 0x00)
        self.bus.write(self.address, self.reg_cfg, 0x01)  # bit 0 input (auto sense), rest outputs

    def press(self, key, hold, gap, sleep):
        try:
            self.bus.write(self.address, self.reg_out, key | LED)
            sleep(hold)
        finally:
            self.bus.write(self.address, self.reg_out, 0x00)
        sleep(gap)

    def auto_on(self):
        return not self.bus.read(self.address, self.reg_in) & 0x01  # 0 means auto is on


class VanTurtleFan:
    """Belief/desired model and the worker that converges one fan.

    post(fn, *args) runs fn on the D-Bus main loop; report(key, value) and set_online(bool)
    are only ever called through it.
    """

    def __init__(self, fan_id, rj45, rj11, post, report, set_online, state_file=None,
                 press_s=0.15, onoff_s=0.75, gap_s=0.25, wake_beep=True, wake_after_s=10.0,
                 homing_presses=10, on_opens_lid=None, rj11_off_closes_lid=None, lid_settle_s=12.0,
                 sleep=time.sleep, clock=time.monotonic):
        self.id, self.rj45, self.rj11 = fan_id, rj45, rj11
        self.post, self.report, self.set_online = post, report, set_online
        self.state_file = state_file
        self.press_s, self.onoff_s, self.gap_s = press_s, onoff_s, gap_s
        self.wake_beep, self.wake_after_s = wake_beep, wake_after_s
        self.homing_presses = homing_presses
        self.on_opens_lid = on_opens_lid  # True / False / None = not known yet
        self.rj11_off_closes_lid = rj11_off_closes_lid  # None = not known yet
        self.lid_settle_s = lid_settle_s  # a full lid stroke; a lid keyed mid-travel reverses hard
        self.sleep, self.clock = sleep, clock

        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.belief = dict.fromkeys(KEYS)  # None = unknown
        self.desired = dict.fromkeys(KEYS)  # None = no wish; nothing is pressed at start
        self.online = False
        self._last_press = None
        self._last_lid_motion = None
        self._homing_left = None
        self._mode_tries = 0
        self._load()

    # ---- called on the main loop -------------------------------------------

    def command(self, key, value):
        with self.lock:
            self.desired[key] = int(value)
            if key == "mode":
                self.desired["on"] = self.desired["lid"] = None  # follow the fan after a mode change
            elif self.belief["mode"] == 1:
                self.desired["mode"] = 0  # touching a manual control leaves auto mode
                self.post(self.report, "mode", 0)
            if self.rj11 and key in ("on", "lid"):
                self.belief[key] = None  # absolute keys available: re-assert on every touch
            if self.rj11 and key == "on" and int(value) == 0 and self.rj11_off_closes_lid:
                self.desired["lid"] = 0  # the fan closes it anyway; show that rather than fight it
                self.post(self.report, "lid", 0)
            if key == "speed" and int(value) == 10:
                self.belief["speed"] = None  # Slower stops at 1, so 10 % can always re-home
        self.wake.set()

    def start(self):
        threading.Thread(target=self._run, name="maxxfan-" + self.id, daemon=True).start()

    # ---- worker ------------------------------------------------------------

    def _run(self):
        while True:
            try:
                if not self.online:
                    self.init()
                if not self.converge_step():
                    self.wake.wait(2.0)
                    self.wake.clear()
                    self.poll()
            except OSError as e:
                log.warning("%s: cannot reach the board (%s): %s", self.id, self.rj45, e)
                if self.online:
                    self.online = False
                    self.post(self.set_online, False)
                self.rj45.bus.reset()
                self.sleep(10)

    def init(self):
        for ch in filter(None, (self.rj45, self.rj11)):
            ch.init()
        mode = int(self.rj45.auto_on())
        with self.lock:
            self.belief["mode"] = mode
            if self.desired["mode"] is None:
                self.desired["mode"] = mode
            known = {k: v for k, v in self.belief.items() if v is not None}
        self.online = True
        self.post(self.set_online, True)
        for key, value in known.items():
            self.post(self.report, key, value)
        log.info("%s: VanTurtle %s%s ready, believed state %s", self.id, self.rj45,
                 " + %s" % self.rj11 if self.rj11 else "", known)

    def poll(self):
        """Idle check of the auto sense line, to follow Auto presses on the keypad or remote."""
        sensed = int(self.rj45.auto_on())
        with self.lock:
            if sensed == self.belief["mode"]:
                return
            self.belief["mode"] = self.desired["mode"] = sensed
            self.desired["on"] = self.desired["lid"] = None
            self._after_auto_change(sensed)
        self.post(self.report, "mode", sensed)
        self.post(self.report, "on", 1)
        self.post(self.report, "lid", 1)
        self._save()

    def converge(self, max_steps=200):
        """Press keys until the belief matches the desired state (used by tests)."""
        for _ in range(max_steps):
            if not self.converge_step():
                return True
        return False

    def converge_step(self):
        """Do at most one key press (or one short sequence). False when nothing is left."""
        with self.lock:
            want = dict(self.desired)
            b = dict(self.belief)
        rj11 = self.rj11

        if want["mode"] is not None and want["mode"] != b["mode"]:
            if self._mode_tries >= 3:
                log.warning("%s: fan did not follow the Auto key, giving up", self.id)
                self._mode_tries = 0
                with self.lock:
                    self.desired["mode"] = b["mode"]
                self.post(self.report, "mode", b["mode"])
                return True
            self._mode_tries += 1
            self._press(self.rj45, AUTO, moves_lid=want["mode"] == 1 and b["lid"] != 1)
            sensed = int(self.rj45.auto_on())
            if sensed == want["mode"]:
                self._mode_tries = 0
            self._update(mode=sensed, auto_changed=sensed != b["mode"])
            return True
        if b["mode"] == 1:
            return False  # the fan's thermostat is in charge

        t = want["on"]
        if t is not None and t != b["on"]:
            off_may_close = self.rj11_off_closes_lid is not False and b["lid"] != 0
            if t == 0 and rj11:
                self._press(rj11, RJ11_OFF, moves_lid=off_may_close)
                self._lid_after_rj11_off(want, b)
            elif b["on"] is None and rj11:
                self._press(rj11, RJ11_OFF, moves_lid=off_may_close)  # known off first, then toggle on
                self._lid_after_rj11_off(want, b)
            elif b["on"] is None:
                self._reset_via_auto(b)
            else:
                self._press(self.rj45, ONOFF, self.onoff_s,
                            moves_lid=t == 1 and self.on_opens_lid is not False and b["lid"] != 1)
                if t == 1:
                    lid = None if rj11 else (1 if self.on_opens_lid else b["lid"])
                    self._update(on=1, lid=lid)
                else:
                    self._update(on=0)
            return True

        t = want["lid"]
        if t is not None and t != b["lid"]:
            if rj11:
                self._press(rj11, RJ11_OPEN if t else RJ11_CLOSE, moves_lid=True)
            else:
                self._press(self.rj45, LID_TOGGLE, moves_lid=True)  # unknown lid: assume it was the other way
            self._update(lid=t)
            return True

        if b["on"] != 1:
            return False  # direction and speed only change while running

        t = want["dir"]
        if t is not None and t != b["dir"]:
            self._press(self.rj45, INOUT)  # unknown direction: assume it was the other way
            self._update(dir=t)
            return True

        t = want["speed"]
        if t is not None and t != b["speed"]:
            if b["speed"] is None:  # unknown: step down to the bottom first
                if self._homing_left is None:
                    self._homing_left = self.homing_presses
                self._press(self.rj45, SLOWER)
                self._homing_left -= 1
                if self._homing_left == 0:
                    self._homing_left = None
                    self._update(speed=10)
            elif t > b["speed"]:
                self._press(self.rj45, FASTER)
                self._update(speed=min(100, b["speed"] + 10))
            else:
                self._press(self.rj45, SLOWER)
                self._update(speed=max(10, b["speed"] - 10))
            return True
        return False

    def _reset_via_auto(self, b):
        """RJ45 only, fan state unknown: Auto on always starts the fan, Auto off leaves it running."""
        if not self.rj45.auto_on():
            self._press(self.rj45, AUTO, moves_lid=b["lid"] != 1)
            if not self.rj45.auto_on():
                return  # swallowed; the next step retries
        self._press(self.rj45, AUTO)
        if self.rj45.auto_on():
            return
        self._update(mode=0, on=1, lid=1)

    def _lid_after_rj11_off(self, want, b):
        """RJ11 Off may also close the lid. If that is not known yet, put the lid back where
        the GUI shows it (after it has finished moving)."""
        if self.rj11_off_closes_lid is True:
            self._update(on=0, lid=0)
        elif self.rj11_off_closes_lid is False:
            self._update(on=0)
        else:
            with self.lock:
                if want["lid"] is None and b["lid"] is not None:
                    self.desired["lid"] = b["lid"]
            self._update(on=0, lid=None)

    def _after_auto_change(self, mode):
        """Auto on starts the fan and opens the lid; leaving auto is assumed to keep it running.
        Called with the lock held. With RJ11, the next touch re-asserts on/lid anyway."""
        self.belief["on"] = self.belief["lid"] = 1

    def _update(self, auto_changed=False, **values):
        with self.lock:
            self.belief.update(values)
            if auto_changed:
                self._after_auto_change(values["mode"])
        if auto_changed:
            self.post(self.report, "on", 1)
            self.post(self.report, "lid", 1)
        self._save()

    def _press(self, channel, key, hold=None, moves_lid=False):
        """moves_lid: this key may set the lid moving. Such keys wait for the previous lid
        stroke to finish; keying the lid mid-travel makes it reverse hard."""
        if moves_lid and self._last_lid_motion is not None:
            wait = self.lid_settle_s - (self.clock() - self._last_lid_motion)
            if wait > 0:
                self.sleep(wait)
        now = self.clock()
        if self.wake_beep and (self._last_press is None or now - self._last_press > self.wake_after_s):
            self.rj45.press(BEEP, self.press_s, self.gap_s, self.sleep)  # a sleeping fan swallows its first key
        channel.press(key, hold or self.press_s, self.gap_s, self.sleep)
        self._last_press = self.clock()
        if moves_lid:
            self._last_lid_motion = self._last_press

    # ---- persistence: the fan keeps its state across a Venus reboot, so must we ----

    def _load(self):
        if not self.state_file:
            return
        try:
            with open(self.state_file) as f:
                saved = json.load(f)
            for key in ("on", "dir", "lid"):
                if saved.get(key) in (0, 1):
                    self.belief[key] = saved[key]
            if saved.get("speed") in range(10, 101, 10):
                self.belief["speed"] = saved["speed"]
        except (OSError, ValueError):
            pass

    def _save(self):
        if not self.state_file:
            return
        try:
            with self.lock:
                data = json.dumps(self.belief)
            tmp = self.state_file + ".tmp"
            with open(tmp, "w") as f:
                f.write(data)
            os.replace(tmp, self.state_file)
        except OSError as e:
            log.warning("%s: cannot save state: %s", self.id, e)
