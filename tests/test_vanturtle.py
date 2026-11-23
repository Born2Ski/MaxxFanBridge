"""Desktop test of the VanTurtle backend against a simulated MaxxFan.

The simulated fan reacts to key presses with toggle semantics, as the real one does.
For every starting state and every command, the fan must end up where the driver
believes it is. The fan's uncertain behaviours are run both ways.

    python3 tests/test_vanturtle.py
"""
import itertools
import os
import random
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "venus", "dbus-maxxfan-bridge"))
import vanturtle as vt  # noqa: E402

TMP = os.path.join(ROOT, ".build", "test-tmp")  # stay inside the project folder


class Clock:
    """Fake time: sleeping advances it."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class SimFan:
    """A MaxxFan Deluxe as seen through its two wall-control jacks."""

    def __init__(self, on=0, speed=3, exhaust=1, lid=0, auto=0, asleep=False,
                 rj11_off_closes_lid=False, on_opens_lid=False, clock=None, lid_travel_s=0.0):
        self.on, self.speed, self.exhaust, self.lid, self.auto = on, speed, exhaust, lid, auto
        self.asleep = asleep
        self.rj11_off_closes_lid, self.on_opens_lid = rj11_off_closes_lid, on_opens_lid
        self.clock, self.lid_travel_s = clock, lid_travel_s
        self.lid_busy_until = None
        self.reversals = 0  # lid keyed while still travelling
        self.presses = []

    def _set_lid(self, value):
        if value == self.lid:
            return
        if self.clock and self.lid_busy_until is not None and self.clock() < self.lid_busy_until:
            self.reversals += 1
        self.lid = value
        if self.clock:
            self.lid_busy_until = self.clock() + self.lid_travel_s

    def press(self, port, key):
        self.presses.append((port, key))
        if self.asleep:  # first key after a while only wakes the fan
            self.asleep = False
            return
        if port == "rj45":
            if key == vt.LID_TOGGLE:
                self._set_lid(1 - self.lid)
            elif key == vt.AUTO:
                self.auto ^= 1
                if self.auto:
                    self.on = 1
                    self._set_lid(1)
            elif key == vt.INOUT:
                self.exhaust ^= 1
            elif key == vt.ONOFF:
                self.on ^= 1
                if self.on and self.on_opens_lid:
                    self._set_lid(1)
            elif key == vt.FASTER and self.on:
                self.speed = min(10, self.speed + 1)
            elif key == vt.SLOWER and self.on:
                self.speed = max(1, self.speed - 1)
            elif key != vt.BEEP:
                raise AssertionError("unknown RJ45 key %#x" % key)
        else:
            if key == vt.RJ11_OFF:
                self.on = 0
                if self.rj11_off_closes_lid:
                    self._set_lid(0)
            elif key == vt.RJ11_OPEN:
                self._set_lid(1)
            elif key == vt.RJ11_CLOSE:
                self._set_lid(0)
            else:
                raise AssertionError("unexpected RJ11 key %#x" % key)

    def sense(self):
        return 0x00 if self.auto else 0x01


class FakeBus:
    """Two VanTurtle boards: 0x27 channel 1 -> RJ45 of the fan, 0x26 channel 1 -> RJ11."""

    def __init__(self, fan):
        self.fan = fan
        self.out = {}
        self.log = []

    def port(self, address):
        return "rj45" if address == 0x27 else "rj11"

    def write(self, address, reg, value):
        self.log.append((address, reg, value))
        if reg in (0x02, 0x03):
            held = self.out.get((address, reg), 0)
            if value & ~vt.LED and held & ~vt.LED:
                raise AssertionError("new key pressed while another is held")
            if value & ~vt.LED:
                assert value & vt.LED, "activity LED should light with each press"
                self.fan.press(self.port(address), value & ~vt.LED)
            self.out[(address, reg)] = value

    def read(self, address, reg):
        assert reg in (0x00, 0x01)
        return self.fan.sense()

    def reset(self):
        pass


def make(fan, rj11=True, clock=None, **kw):
    bus = FakeBus(fan)
    reports = {}
    online = []
    worker = vt.VanTurtleFan(
        "fan1", vt.Channel(bus, 0x27, 1), vt.Channel(bus, 0x26, 1) if rj11 else None,
        post=lambda fn, *a: fn(*a), report=lambda k, v: reports.__setitem__(k, v),
        set_online=online.append,
        sleep=clock.sleep if clock else (lambda s: None),
        clock=clock if clock else (lambda: 0.0), **kw)
    worker.init()
    return worker, bus, reports, online


def check(fan, worker, target, check_dir):
    assert worker.converge(), "did not converge"
    b = worker.belief
    on, lid, speed, direction = target
    assert fan.on == on, ("on", fan.__dict__, b, target)
    assert fan.lid == lid, ("lid", fan.__dict__, b, target)
    if on:
        assert fan.speed * 10 == speed, ("speed", fan.__dict__, b, target)
        if check_dir:
            assert fan.exhaust == direction, ("dir", fan.__dict__, b, target)


def test_init_order_and_release():
    fan = SimFan()
    worker, bus, reports, online = make(fan)
    assert bus.log[:2] == [(0x27, 0x02, 0x00), (0x27, 0x06, 0x01)], bus.log[:2]
    assert online == [True] and reports == {"mode": 0}
    assert fan.presses == [], "nothing may be pressed at start"

    class Boom(Exception):
        pass

    def bad_sleep(_s):
        raise Boom()

    try:
        worker.rj45.press(vt.ONOFF, 0.15, 0.25, bad_sleep)
    except Boom:
        pass
    assert bus.out[(0x27, 0x02)] == 0, "key must be released even if the hold is interrupted"


def test_all_starts_both_ports():
    """Unknown belief (fresh install): RJ11 + RJ45 must reach every on/lid/speed target,
    whether or not the driver has been told how RJ11 Off treats the lid."""
    runs = 0
    for closes, opens, asleep, told in itertools.product((False, True), repeat=4):
        for on0, speed0, ex0, lid0 in itertools.product((0, 1), (1, 4, 10), (0, 1), (0, 1)):
            for target in itertools.product((0, 1), (0, 1), (10, 50, 100), (0, 1)):
                fan = SimFan(on0, speed0, ex0, lid0, asleep=asleep,
                             rj11_off_closes_lid=closes, on_opens_lid=opens)
                worker, *_ = make(fan, rj11_off_closes_lid=closes if told else None)
                on, lid, speed, direction = target
                for key, value in (("speed", speed), ("dir", direction), ("on", on), ("lid", lid)):
                    worker.command(key, value)
                check(fan, worker, target, check_dir=False)  # unknown direction is the known gap
                # A second round of commands, from where the first left off
                target2 = (1 - on, 1 - lid, 110 - speed, direction)
                for key, value in zip(("on", "lid", "speed"), target2):
                    worker.command(key, value)
                check(fan, worker, target2, check_dir=False)
                runs += 1
    return runs


def test_random_sequences(rj11, closes, opens, seed, told=False, settle_s=None):
    """Belief starts correct (from the state file); long random command sequences must hold.
    With settle_s, time is simulated and the lid must never be keyed mid-travel."""
    rnd = random.Random(seed)
    clock = Clock() if settle_s is not None else None
    fan = SimFan(on=1, speed=5, exhaust=1, lid=1, rj11_off_closes_lid=closes, on_opens_lid=opens,
                 clock=clock, lid_travel_s=10.0)
    kw = dict(on_opens_lid=opens, rj11_off_closes_lid=closes if told else None)
    if settle_s is not None:
        kw["lid_settle_s"] = settle_s
    os.makedirs(TMP, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TMP) as tmp:
        state = os.path.join(tmp, "state.json")
        with open(state, "w") as f:
            f.write('{"on": 1, "speed": 50, "dir": 1, "lid": 1, "mode": null}')
        worker, bus, reports, _ = make(fan, rj11=rj11, state_file=state, clock=clock, **kw)
        assert reports == {"on": 1, "speed": 50, "dir": 1, "lid": 1, "mode": 0}, reports
        target = [1, 1, 50, 1]
        for _ in range(300):
            i = rnd.randrange(4)
            target[i] = rnd.choice((10, 20, 50, 90, 100)) if i == 2 else rnd.randrange(2)
            worker.command(("on", "lid", "speed", "dir")[i], target[i])
            if rj11 and told and closes and i == 0 and target[0] == 0:
                target[1] = 0  # told that Off closes the lid: the card shows it closed
                assert reports["lid"] == 0
            if rnd.random() < 0.6:  # sometimes several commands arrive before the worker runs
                check(fan, worker, tuple(target), check_dir=True)
            if clock:
                clock.sleep(rnd.choice((0.5, 3, 20)))  # the user pauses between touches
        check(fan, worker, tuple(target), check_dir=True)
        if clock:
            assert fan.reversals == 0, "lid keyed %d times while travelling" % fan.reversals

        # The state file carries the belief over a restart without pressing anything
        presses = len(fan.presses)
        worker2, *_ = make(fan, rj11=rj11, state_file=state, clock=clock, **kw)
        assert len(fan.presses) == presses
        assert {k: worker2.belief[k] for k in ("on", "lid", "dir")} == \
            {"on": fan.on, "lid": fan.lid, "dir": fan.exhaust}


def test_lid_settle():
    """Off (which may close the lid) followed by Open must wait for the lid to finish."""
    for told in (False, True):
        clock = Clock()
        fan = SimFan(on=1, speed=5, lid=1, rj11_off_closes_lid=True, clock=clock, lid_travel_s=10.0)
        worker, *_ = make(fan, clock=clock, lid_settle_s=12.0,
                          rj11_off_closes_lid=True if told else None)
        worker.belief.update(on=1, speed=50, dir=1, lid=1)
        worker.command("on", 0)
        worker.command("lid", 1)  # user wants it off but open
        assert worker.converge()
        assert fan.on == 0 and fan.lid == 1 and fan.reversals == 0, fan.__dict__
    for seed in range(3):
        for opens in (False, True):
            test_random_sequences(True, True, opens, seed, settle_s=12.0)
            test_random_sequences(True, True, opens, seed, told=True, settle_s=12.0)
            test_random_sequences(False, False, opens, seed, settle_s=12.0)


def test_rj45_only_unknown_on():
    """No RJ11: an unknown on/off state is resolved through Auto, which always starts the fan."""
    for on0 in (0, 1):
        for target in (0, 1):
            fan = SimFan(on=on0, lid=1)
            worker, *_ = make(fan, rj11=False)
            worker.command("on", target)
            assert worker.converge()
            assert fan.on == target and fan.auto == 0, (on0, target, fan.__dict__)


def test_keypad_drift():
    """Someone used the ceiling keypad: the belief is wrong. The GUI can only send a value
    different from what it shows, so the user taps the control twice. With RJ11, each tap
    must leave the fan where the card says."""
    for closes in (False, True):
        fan = SimFan(on=1, speed=5, lid=1, rj11_off_closes_lid=closes)  # really running, open
        worker, *_ = make(fan)
        worker.belief.update(on=0, speed=50, dir=1, lid=0)  # card shows off and closed
        worker.command("on", 1)  # first tap: card shows on
        assert worker.converge() and fan.on == 1, fan.__dict__
        worker.command("on", 0)  # second tap: card shows off
        assert worker.converge() and fan.on == 0, fan.__dict__
        worker.command("lid", 1)
        assert worker.converge() and fan.lid == 1
        worker.command("lid", 0)
        assert worker.converge() and fan.lid == 0
    # Speed changed on the keypad: going to 10 % re-homes, after which steps are right again
    fan = SimFan(on=1, speed=8)
    worker, *_ = make(fan)
    worker.belief.update(on=1, speed=30, dir=1, lid=1)
    worker.command("speed", 10)
    assert worker.converge() and fan.speed == 1
    worker.command("speed", 60)
    assert worker.converge() and fan.speed == 6


def test_auto_mode():
    for rj11 in (True, False):
        fan = SimFan(on=0, lid=0)
        worker, _bus, reports, _ = make(fan, rj11=rj11)
        worker.command("mode", 1)
        assert worker.converge() and fan.auto == 1 and worker.belief["mode"] == 1
        assert reports["on"] == 1 and reports["lid"] == 1, "card must show what auto mode did"
        # While in auto nothing else is pressed
        n = len(fan.presses)
        assert worker.converge() and len(fan.presses) == n
        # Touching a manual control leaves auto first, then applies it
        worker.command("on", 0)
        assert reports["mode"] == 0
        assert worker.converge()
        assert fan.auto == 0 and fan.on == 0, fan.__dict__
        # Auto pressed on the keypad is noticed by the idle poll and not fought
        fan.auto, fan.on, fan.lid = 1, 1, 1
        reports.clear()
        worker.poll()
        assert reports == {"mode": 1, "on": 1, "lid": 1} and worker.desired["mode"] == 1
        n = len(fan.presses)
        assert worker.converge() and len(fan.presses) == n


def test_auto_key_ignored():
    """If the fan never follows the Auto key, give up and show the real mode."""
    fan = SimFan()
    worker, _bus, reports, _ = make(fan, wake_beep=False)
    fan.press = lambda port, key: None
    worker.command("mode", 1)
    assert worker.converge()
    assert worker.desired["mode"] == 0 and reports["mode"] == 0


def test_wake_beep_needed():
    """Without the leading Beep, a sleeping fan swallows a key and the count is off."""
    fan = SimFan(on=1, speed=5, asleep=True)
    worker, *_ = make(fan, rj11=False, wake_beep=False)
    worker.belief.update(on=1, speed=50, dir=1, lid=0)
    worker.command("speed", 80)
    worker.converge()
    assert fan.speed == 7, "expected the simulated swallow to show (sanity check of the test)"


def test_parse_channel():
    assert vt.parse_channel("0x27:2") == (0x27, 2)
    assert vt.parse_channel("0x26") == (0x26, 1)
    for bad in ("0x30:1", "0x27:3", "zz"):
        try:
            vt.parse_channel(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def main():
    test_init_order_and_release()
    runs = test_all_starts_both_ports()
    for rj11, closes, opens, told in itertools.product((True, False), repeat=4):
        if not rj11 and (closes or told):
            continue  # RJ11 behaviour is irrelevant without an RJ11 port
        for seed in range(5):
            test_random_sequences(rj11, closes, opens, seed, told=told)
    test_lid_settle()
    test_rj45_only_unknown_on()
    test_keypad_drift()
    test_auto_mode()
    test_auto_key_ignored()
    test_wake_beep_needed()
    test_parse_channel()
    print("vanturtle: all checks passed (%d start/target combinations)" % runs)


if __name__ == "__main__":
    main()
