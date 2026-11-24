"""Desktop test of the VanTurtle WiFi backend (option W) against a simulated controller.

The simulated controller behaves as VanTurtle documents its WiFi firmware: one retained topic
per field in both directions, full state on connect, a keepalive, an echo-suppress window
after each of its own publishes, and a lid that only toggles. Direction and Auto are run both
as a toggle and as an absolute value, since VanTurtle does not say which they are.

    python3 tests/test_vtwifi.py
"""
import configparser
import os
import random
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "venus", "dbus-maxxfan-bridge"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import vtwifi  # noqa: E402

TMP = os.path.join(ROOT, ".build", "test-tmp")  # stay inside the project folder
P = "maxxfan/fan1/vt"


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Broker:
    """MQTT 3.1.1 as far as needed: retained values, and live delivery, in order, to every
    matching subscriber including the publisher itself."""

    def __init__(self):
        self.retained, self.subs, self.queue, self.log = {}, [], [], []

    def subscribe(self, name, prefix, deliver):
        self.subs.append((name, prefix, deliver))
        for topic, payload in sorted(self.retained.items()):
            if topic.startswith(prefix + "/"):
                self.queue.append((deliver, topic, payload, True))

    def publish(self, sender, topic, payload, retain=False):
        self.log.append((sender, topic, payload))
        if retain:
            self.retained[topic] = payload
        for _name, prefix, deliver in self.subs:
            if topic.startswith(prefix + "/"):
                self.queue.append((deliver, topic, payload, False))

    def flush(self):
        while self.queue:
            deliver, topic, payload, retained = self.queue.pop(0)
            deliver(topic, payload, retained)

    def sent_by(self, sender):
        return [(t[len(P) + 1:], p) for s, t, p in self.log if s == sender]


class SimController:
    """The VanTurtle Smart Controller with WiFi firmware, and the fan behind it."""

    def __init__(self, broker, clock, on=0, speed=3, direction=0, auto=0, lid=0,
                 dir_toggles=True, auto_toggles=False, on_opens_lid=False, suppress_s=0.5,
                 report_steps=False):
        self.b, self.clock = broker, clock
        self.on, self.speed, self.dir, self.auto, self.lid = on, speed, direction, auto, lid
        self.dir_toggles, self.auto_toggles, self.on_opens_lid = dir_toggles, auto_toggles, on_opens_lid
        self.suppress_s, self.report_steps = suppress_s, report_steps
        self.last_pub = None
        self.drop_next = 0  # commands lost, as if the WiFi dropped them
        self.dropped = []
        self.lid_moves = []

    def connect(self):
        self.b.subscribe("ctl", P, self._receive)
        for leaf in ("on", "speed", "dir", "auto"):
            self._pub(leaf)

    def alive(self):
        self.b.publish("ctl", P + "/alive", "1")
        self.last_pub = self.clock()

    def _pub(self, leaf):
        value = {"on": self.on, "speed": self.speed, "dir": self.dir, "auto": self.auto}[leaf]
        self.b.publish("ctl", "%s/%s" % (P, leaf), str(value), retain=True)
        self.last_pub = self.clock()

    def _receive(self, topic, payload, _retained):
        if self.last_pub is not None and self.clock() - self.last_pub < self.suppress_s:
            return  # echo suppress: everything is ignored, our own echoes and commands alike
        leaf = topic[len(P) + 1:]
        if leaf not in ("on", "speed", "dir", "auto", "lid"):
            return
        if self.drop_next:
            self.drop_next -= 1
            self.dropped.append(leaf)
            return
        if self.auto and leaf != "auto":
            return  # assumed: in Auto the thermostat is in charge and manual keys do nothing
        if leaf == "lid":
            self.lid ^= 1
            self.lid_moves.append(self.clock())
        elif leaf == "dir":
            new = self.dir ^ 1 if self.dir_toggles else int(payload)
            if new != self.dir:
                self.dir = new
                self._pub("dir")
        elif leaf == "speed":
            target = int(payload)
            if target != self.speed:
                while self.report_steps and abs(target - self.speed) > 1:
                    self.speed += 1 if target > self.speed else -1
                    self._pub("speed")
                self.speed = target
                self._pub("speed")
        elif leaf == "on":
            self.set_on(int(payload))
        elif leaf == "auto":
            self.set_auto(self.auto ^ 1 if self.auto_toggles else int(payload))

    # also what the ceiling keypad does
    def set_on(self, value):
        if value != self.on:
            self.on = value
            if value and self.on_opens_lid and not self.lid:
                self.lid = 1
                self.lid_moves.append(self.clock())
            self._pub("on")

    def set_auto(self, value):
        if value != self.auto:
            self.auto = value
            self._pub("auto")
            if value:
                if not self.lid:
                    self.lid = 1
                    self.lid_moves.append(self.clock())
                self.set_on(1)


class Rig:
    def __init__(self, sim_kw=None, fan_kw=None, connect=True):
        self.clock = Clock()
        self.b = Broker()
        self.sim = SimController(self.b, self.clock, **(sim_kw or {}))
        self.shown, self.online_log = {}, []
        self.fan = vtwifi.VtWifiFan(
            "fan1", P, lambda topic, payload: self.b.publish("drv", topic, payload),
            self.shown.__setitem__, self.online_log.append, clock=self.clock, **(fan_kw or {}))
        if connect:
            self.sim.connect()
            self.b.flush()
        self.b.subscribe("drv", P, lambda t, p, r: self.fan.on_message(t[len(P) + 1:], p, r))
        self.b.flush()

    def run(self, seconds, alive_every=60):
        for _ in range(int(seconds)):
            self.clock.t += 1
            if alive_every and int(self.clock.t) % alive_every == 0:
                self.sim.alive()
            self.b.flush()
            self.fan.tick()
            self.b.flush()

    def touch(self, key, value):
        self.fan.command(key, value)
        self.b.flush()

    def actual(self):
        s = self.sim
        return {"on": s.on, "speed": s.speed * 10, "dir": s.dir, "mode": s.auto, "lid": s.lid}

    def drv(self):
        return self.b.sent_by("drv")


def test_parse():
    assert vtwifi.parse("speed", "7") == 70 and vtwifi.parse("speed", "7.0") == 70
    assert vtwifi.parse("speed", "0") is None and vtwifi.parse("speed", "11") is None
    assert vtwifi.parse("speed", "6.5") is None and vtwifi.parse("speed", "x") is None
    assert vtwifi.parse("on", "1") == 1 and vtwifi.parse("on", "true") == 1 and vtwifi.parse("mode", "OFF") == 0
    assert vtwifi.parse("dir", "2") is None and vtwifi.parse("dir", "") is None
    assert vtwifi.encode("speed", 70) == "7" and vtwifi.encode("on", 1) == "1"


def test_start_retained_then_live():
    r = Rig(sim_kw=dict(on=1, speed=6, direction=1, auto=0))
    # The controller's state was retained: shown at once, but not online until it speaks live.
    assert r.shown == {"on": 1, "speed": 60, "dir": 1, "mode": 0}, r.shown
    assert r.online_log == [] and not r.fan.online
    r.run(60)  # first keepalive
    assert r.online_log == [True] and r.fan.online
    assert r.drv() == [], "nothing is sent at start"


def test_command_echo_and_confirm():
    r = Rig(sim_kw=dict(on=1, speed=3, report_steps=True))
    r.run(60)
    r.touch("speed", 70)
    assert r.drv() == [("speed", "7")]
    assert r.sim.speed == 7 and r.shown["speed"] == 70
    assert r.fan.inflight is None and r.fan.wish == {}, "confirmed by the controller, not by our own echo"
    r.run(30)
    assert r.drv() == [("speed", "7")], "no resend after a confirmation"


def test_own_echo_is_not_a_confirmation():
    r = Rig(sim_kw=dict(on=1, speed=3))
    r.run(60)
    r.sim.drop_next = 1
    r.touch("speed", 50)
    assert r.fan.inflight and r.fan.inflight[:2] == ["speed", 50], "our echo must not confirm"
    assert r.shown["speed"] == 50, "the wish is shown while waiting"
    r.run(11)  # confirm_s passes: sent once more
    assert r.drv() == [("speed", "5"), ("speed", "5")] and r.sim.speed == 5
    assert r.fan.wish == {} and r.shown["speed"] == 50


def test_give_up_shows_reality():
    r = Rig(sim_kw=dict(on=0, speed=3))
    r.run(60)
    r.sim.drop_next = 2
    r.touch("on", 1)
    assert r.shown["on"] == 1
    r.run(25)
    assert r.drv() == [("on", "1"), ("on", "1")], "absolute commands are sent twice at most"
    assert r.shown["on"] == 0 and r.fan.wish == {} and r.fan.inflight is None


def test_toggles_are_never_repeated():
    for toggles in (True, False):
        r = Rig(sim_kw=dict(on=1, direction=0, dir_toggles=toggles))
        r.run(60)
        r.sim.drop_next = 1
        r.touch("dir", 1)
        r.run(25)
        assert r.drv() == [("dir", "1")], "a repeated toggle would undo the first"
        assert r.shown["dir"] == 0 == r.sim.dir, "screen back to the controller's report"
        # Flip twice quickly: right for a toggle and for an absolute value alike.
        r.touch("dir", 1)
        r.touch("dir", 0)
        r.run(30)
        assert r.sim.dir == 0 and r.shown["dir"] == 0, (toggles, r.drv())
        r.touch("dir", 1)
        r.run(5)
        r.touch("dir", 0)
        r.run(30)
        assert r.sim.dir == 0 and r.shown["dir"] == 0, (toggles, r.drv())


def test_auto_is_never_repeated():
    """VanTurtle's web app toggles Auto, and the MQTT docs do not say. A repeat could undo it."""
    for toggles in (True, False):
        r = Rig(sim_kw=dict(on=0, auto=0, auto_toggles=toggles))
        r.run(60)
        r.sim.drop_next = 1
        r.touch("mode", 1)
        r.run(25)
        assert r.drv() == [("auto", "1")], (toggles, r.drv())
        assert r.shown["mode"] == 0 == r.sim.auto, "screen back to the controller's report"
        r.touch("mode", 1)
        r.run(5)
        assert r.sim.auto == 1 and r.shown["mode"] == 1
        r.touch("mode", 0)
        r.run(5)
        assert r.sim.auto == 0 and r.shown["mode"] == 0, (toggles, r.drv())


def test_swap_direction():
    """swap_direction = yes: the controller's dir 0 is shown and sent as exhaust (1)."""
    for toggles in (True, False):
        r = Rig(sim_kw=dict(on=1, direction=0, dir_toggles=toggles), fan_kw=dict(dir_swapped=True))
        assert r.shown["dir"] == 1, "controller 0 shows as exhaust"
        r.run(60)
        r.touch("dir", 0)
        r.run(5)
        assert r.sim.dir == 1 and r.shown["dir"] == 0, (toggles, r.drv())
        assert r.drv() == [("dir", "1")], "sent in the controller's terms"
        assert r.fan.wish == {} and r.fan.inflight is None, "confirmed"


def test_first_start_assumes_lid_closed():
    """No state file yet: the lid counts as closed (SETUP.md has the owner close it before the
    first start), so a preset's "closed" sends nothing and "open" sends one toggle."""
    r = Rig(sim_kw=dict(lid=0), fan_kw=dict(lid_settle_s=0))
    r.run(60)
    assert r.shown.get("lid") == 0, "the card shows closed"
    r.fan.command("lid", 0)  # what a preset does; the GUI only writes changes
    r.run(5)
    assert r.sim.lid == 0 and ("lid", "1") not in r.drv(), "closing a closed lid must not toggle it"
    r.touch("lid", 1)
    r.run(5)
    assert r.sim.lid == 1 and r.shown["lid"] == 1


def test_one_command_at_a_time_after_quiet():
    """Leaving Auto makes the controller publish, which opens its echo-suppress window. The
    next command must wait, or the controller would drop it."""
    r = Rig(sim_kw=dict(on=1, auto=1, lid=1, speed=5, suppress_s=1.5), fan_kw=dict(lid_settle_s=0))
    r.fan.lid = 1
    r.run(60)
    r.touch("speed", 80)
    r.touch("lid", 0)
    assert r.shown["mode"] == 0 and r.shown["speed"] == 80 and r.shown["lid"] == 0
    assert r.drv() == [("auto", "0")], "only one command in flight"
    r.run(10)
    assert r.sim.auto == 0 and r.sim.lid == 0 and r.sim.speed == 8, r.drv()
    assert [k for k, _ in r.drv()] == ["auto", "lid", "speed"], "Auto left first, then the rest"


def test_selecting_auto_drops_manual_wishes():
    r = Rig(sim_kw=dict(on=0, auto=0, lid=0), fan_kw=dict(lid_settle_s=0))
    r.fan.lid = 0
    r.run(60)
    r.sim.drop_next = 1
    r.touch("speed", 90)  # lost; would be resent
    r.touch("mode", 1)
    r.run(30)
    assert r.sim.auto == 1 and r.sim.on == 1
    assert ("speed", "9") not in r.drv()[1:], "after choosing Auto the thermostat is in charge"
    assert r.shown["lid"] == 1 and r.fan.lid == 1, "Auto opens the lid"


def test_lid_belief_settle_and_persistence():
    os.makedirs(TMP, exist_ok=True)
    path = os.path.join(TMP, "vtwifi-state.json")
    if os.path.exists(path):
        os.remove(path)
    r = Rig(sim_kw=dict(lid=0), fan_kw=dict(state_file=path, lid_settle_s=12))
    r.run(60)
    r.touch("lid", 1)
    assert r.sim.lid == 1 and r.fan.lid == 1 and r.drv() == [("lid", "1")]
    r.run(3)
    r.touch("lid", 0)
    assert r.sim.lid == 1, "must wait for the lid to finish moving"
    assert r.shown["lid"] == 0, "the card shows the wish meanwhile"
    r.run(12)
    assert r.sim.lid == 0 and r.fan.lid == 0
    gaps = [b - a for a, b in zip(r.sim.lid_moves, r.sim.lid_moves[1:])]
    assert all(g >= 12 for g in gaps), gaps
    again = vtwifi.VtWifiFan("fan1", P, None, {}.__setitem__, None, state_file=path)
    assert again.lid == 0, "lid belief survives a restart"
    # Changing your mind before the toggle went out sends nothing.
    r.touch("lid", 1)
    assert r.sim.lid == 0  # settle wait after the previous stroke
    r.touch("lid", 0)
    r.run(20)
    assert r.drv().count(("lid", "1")) == 2 and r.sim.lid == 0


def test_on_opens_lid():
    r = Rig(sim_kw=dict(on=0, lid=0, on_opens_lid=True), fan_kw=dict(on_opens_lid=True, lid_settle_s=12))
    r.fan.lid = 0
    r.run(60)
    r.touch("on", 1)
    assert r.sim.lid == 1 and r.fan.lid == 1 and r.shown["lid"] == 1
    r.touch("lid", 0)
    r.run(5)
    assert r.sim.lid == 1, "the lid opened with the fan; wait for that stroke"
    r.run(10)
    assert r.sim.lid == 0
    # Retained values seen at start are not a transition.
    r2 = Rig(sim_kw=dict(on=1, lid=0), fan_kw=dict(on_opens_lid=True))
    r2.fan.lid = 0
    r2.run(60)
    assert r2.fan.lid == 0


def test_keypad_is_followed_not_fought():
    r = Rig(sim_kw=dict(on=1, speed=4))
    r.run(60)
    r.touch("speed", 60)
    r.run(5)
    r.sim.set_on(0)  # someone presses On/Off on the ceiling
    r.sim.set_auto(1)
    r.b.flush()
    assert r.shown["on"] == 1 and r.shown["mode"] == 1, "auto starts the fan"
    r.sim.set_auto(0)
    r.sim.set_on(0)
    r.b.flush()
    r.run(60)
    assert r.shown["on"] == 0 and r.shown["mode"] == 0
    assert r.drv() == [("speed", "6")], "the driver never re-sends after the fan reported"


def test_offline_and_back():
    r = Rig(sim_kw=dict(on=1, speed=4))
    r.run(60)
    r.sim.drop_next = 5
    r.touch("speed", 90)
    r.run(150, alive_every=0)  # controller silent
    assert r.online_log == [True, False] and r.shown["speed"] == 40
    assert r.fan.wish == {} and r.fan.inflight is None
    r.run(60)
    assert r.online_log == [True, False, True]
    r.fan.broker_lost()
    assert r.online_log[-1] is False
    r.fan.command("speed", 50)  # the GUI refuses writes while offline; even so, nothing goes out
    assert r.drv()[-1] != ("speed", "5")


def test_bad_payloads_ignored():
    r = Rig(sim_kw=dict(on=1, speed=4))
    r.run(60)
    for leaf, payload in (("speed", "0"), ("speed", "fast"), ("on", "2"), ("dir", ""), ("power", "12.5")):
        r.b.publish("ctl", "%s/%s" % (P, leaf), payload)
        r.sim.last_pub = r.clock()  # the controller's own publish: its echo suppress ignores it
    r.b.flush()
    assert r.shown["speed"] == 40 and r.shown["on"] == 1


def test_stale_echo_expires():
    r = Rig(sim_kw=dict(on=1, speed=4))
    r.run(60)
    r.fan._publish_leaf("speed", "7", r.clock())  # pretend our echo got lost
    r.b.queue.clear()
    r.run(6)
    r.sim.speed = 6
    r.b.publish("ctl", P + "/speed", "7", retain=True)  # the keypad, later, lands on 7
    r.b.flush()
    assert r.shown["speed"] == 70, "an expired echo must not swallow a real report"


def test_random_sequences():
    """Whatever is touched and whatever gets lost, once things settle the card shows the fan
    as it is (except a lost lid toggle, which nothing can detect). When nothing is lost, the
    fan ends where the last touches asked."""
    keys = ("on", "speed", "dir", "lid", "mode")
    for seed in range(300):
        rnd = random.Random(seed)
        start = dict(on=rnd.randint(0, 1), speed=rnd.randint(1, 10), direction=rnd.randint(0, 1),
                     auto=rnd.randint(0, 1), lid=rnd.randint(0, 1))
        opens = rnd.random() < 0.5
        lossy = rnd.random() < 0.5
        r = Rig(sim_kw=dict(start, dir_toggles=rnd.random() < 0.5, auto_toggles=rnd.random() < 0.5,
                            on_opens_lid=opens, report_steps=rnd.random() < 0.5),
                fan_kw=dict(on_opens_lid=opens, lid_settle_s=rnd.choice((0, 12))))
        r.fan.lid = start["lid"]
        r.run(60)
        last = {}
        for _ in range(rnd.randint(1, 8)):
            key = rnd.choice(keys)
            value = rnd.choice(range(10, 101, 10)) if key == "speed" else rnd.randint(0, 1)
            if lossy and rnd.random() < 0.3:
                r.sim.drop_next = rnd.randint(1, 2)
            if value == r.shown.get(key):
                continue  # the GUI only writes changes
            r.touch(key, value)
            if key == "mode" and value == 1:
                last = {"mode": 1}
            else:
                if r.shown.get("mode") == 0:
                    last["mode"] = 0
                last[key] = value
                if key == "on" and value == 1 and opens:
                    last.pop("lid", None)  # switching on opens the lid: no fixed expectation
            r.run(rnd.choice((0, 1, 3, 15)))
        r.sim.drop_next = 0
        r.run(90)
        actual = r.actual()
        assert r.fan.wish == {} and r.fan.inflight is None, (seed, r.fan.wish, r.fan.inflight)
        for key in keys:
            if key == "lid" and "lid" in r.sim.dropped:
                continue
            assert r.shown[key] == actual[key], (seed, key, r.shown, actual, r.drv())
        if not lossy:
            for key, value in last.items():
                if actual["mode"] == 1 and key != "mode":
                    continue  # the thermostat runs the fan
                assert actual[key] == value, (seed, key, last, actual, r.drv())


def test_driver_integration():
    from test_driver import FakeGLib, load_driver
    d = load_driver()
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    cfg.read_string("[fan1]\nname = Galley fan\nbackend = vanturtle-wifi\n"
                    "on_opens_lid = yes\nlid_settle_s = 15\n"
                    "[fan2]\nbackend = vanturtle-wifi\ntopic = van/roof/   ; trailing slash\n"
                    "swap_direction = yes\n")
    sent, clock = [], Clock()
    client = types.SimpleNamespace(publish=lambda t, p, qos=0: sent.append((t, p, qos)),
                                   subscribe=lambda topics: sent.append(("SUB", topics, 0)))
    vt = {}
    bridge = d.Bridge({}, client, vt)
    fan, worker = d.make_vtwifi_fan("fan1", cfg, None, 60, bridge.publish_raw, clock=clock)
    fan2, worker2 = d.make_vtwifi_fan("fan2", cfg, None, 61, bridge.publish_raw, clock=clock)
    worker.state_file = worker2.state_file = None
    vt[worker.prefix], vt[worker2.prefix] = worker, worker2
    svc, out = fan.svc, "/SwitchableOutput/"

    assert worker.prefix == "maxxfan/fan1/vt" and worker2.prefix == "van/roof"
    assert worker.on_opens_lid is True and worker.lid_settle_s == 15 and worker2.on_opens_lid is None
    assert worker.dir_swapped is False and worker2.dir_swapped is True
    assert svc["/Mgmt/Connection"] == "VanTurtle WiFi maxxfan/fan1/vt"
    assert not any("setpoint" in p for p in svc.paths), "no setpoint on VanTurtle fans"
    bridge._on_connect(client)
    topics = sent.pop()[1]
    assert ("maxxfan/fan1/vt/#", 1) in topics and ("van/roof/#", 1) in topics

    # Retained state shows, card stays disconnected until the controller speaks live.
    for leaf, value in (("on", "1"), ("speed", "4"), ("dir", "1"), ("auto", "0")):
        bridge.dispatch("maxxfan/fan1/vt/" + leaf, value, True)
    assert svc[out + "speed/Dimming"] == 40 and svc[out + "fan/State"] == 1 and svc["/Connected"] == 0
    assert svc.gui_write(out + "speed/Dimming", 70) is False, "refused while offline"
    bridge.dispatch("maxxfan/fan1/vt/alive", "1")
    assert svc["/Connected"] == 1 and fan2.svc["/Connected"] == 0

    # A touch goes out under the controller's topic, in its units.
    clock.t += 5
    assert svc.gui_write(out + "speed/Dimming", 70) is True
    assert sent == [("maxxfan/fan1/vt/speed", "7", 1)], sent
    bridge.dispatch("maxxfan/fan1/vt/speed", "7")  # our own echo
    FakeGLib.fire_timers()  # the Fan's 5 s fallback must keep showing the wish
    assert svc[out + "speed/Dimming"] == 70 and worker.inflight is not None
    bridge.dispatch("maxxfan/fan1/vt/speed", "7", False)  # the controller confirms
    assert worker.inflight is None and svc[out + "speed/Dimming"] == 70

    # Fan 2's topics do not leak into fan 1.
    bridge.dispatch("van/roof/speed", "2", True)
    assert fan2.svc[out + "speed/Dimming"] == 20 and svc[out + "speed/Dimming"] == 70

    # The once-a-second tick drives timeouts; the broker going away takes everything offline.
    clock.t += 3
    assert svc.gui_write(out + "lid/State", 1) is True
    assert sent[-1] == ("maxxfan/fan1/vt/lid", "1", 1) and svc[out + "lid/State"] == 1
    assert bridge.tick() is True
    bridge._all_offline()
    assert svc["/Connected"] == 0 and fan2.svc["/Connected"] == 0
    print("vtwifi: driver integration passed")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and k != "test_driver_integration"]
    for test in tests:
        test()
    test_driver_integration()
    print("vtwifi: all %d checks passed" % (len(tests) + 1))


if __name__ == "__main__":
    main()
