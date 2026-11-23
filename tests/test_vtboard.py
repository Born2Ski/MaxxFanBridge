"""Desktop test of option E: the VanTurtle board at the fan, reached through an ESP32 over MQTT.

The fan is test_vanturtle's simulated MaxxFan. The ESP32 is simulated by SimRelay, which
follows the same rules as archive/firmware/vanturtle_relay.h (tested in archive/tests/test_relay.cpp).
The messages between driver and ESP32 can be lost; the fan must still end up where the
driver believes it is, and no key may be pressed twice because an answer went missing.

    python3 tests/test_vtboard.py
"""
import configparser
import json
import os
import random
import sys
import types

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "venus", "dbus-maxxfan-bridge"))
import test_vanturtle as tv  # noqa: E402
import vanturtle as vt  # noqa: E402
import vtboard  # noqa: E402


class Clock(tv.Clock):
    """Fake time that also runs the ESP32's 10 s heartbeat while it passes."""

    def __init__(self):
        super().__init__()
        self.every_10s = []

    def sleep(self, s):
        end = self.t + s
        while (self.t // 10 + 1) * 10 <= end:
            self.t = (self.t // 10 + 1) * 10
            for fn in list(self.every_10s):
                fn()
        self.t = end


class SimRelay:
    """The ESP32 beside the board, as archive/firmware/vanturtle-board.yaml behaves."""

    REMEMBER = 4

    def __init__(self, fan, clock, ports=("rj45", "rj11")):
        self.fan, self.clock = fan, clock
        self.ports = {1: ports[0], 2: ports[1]}
        self.link = None
        self.answers = []  # newest first, like Relay::answers
        self.i2c_ok = True
        self.refuse_next = False  # the key write fails but the bus still reads: ok false, i2c true
        self.received = []  # every press message that reached the ESP32 or was lost on the way
        self.executed = []  # seqs actually pressed
        self.drop = []  # scripted losses, consumed in order: "press" or "done"
        self.loss = None  # (random.Random, probability) for random losses
        self.heartbeat = True
        clock.every_10s.append(lambda: self.heartbeat and self.state())

    def boot(self, link):
        self.link = link
        link.on_message("status", "online", True)
        self.state()

    def sense(self, ch):
        return self.fan.sense() if self.ports[ch] == "rj45" else 0xFF

    def state(self):
        self.link.on_message("state", json.dumps(
            {"in1": self.sense(1), "in2": self.sense(2), "i2c": self.i2c_ok}), True)

    def _lost(self, what):
        if self.drop and self.drop[0] == what:
            self.drop.pop(0)
            return True
        return bool(self.loss) and self.loss[0].random() < self.loss[1]

    def receive(self, topic, payload):
        assert topic == self.link.prefix + "/press", topic
        msg = json.loads(payload)
        assert set(msg) == {"seq", "ch", "key", "ms", "gap"}, msg
        self.received.append(msg)
        if self._lost("press"):
            return
        seq = msg["seq"]
        answer = next((a for a in self.answers if a["seq"] == seq), None)
        if answer is None:
            ch, key = msg["ch"], msg["key"]
            assert ch in (1, 2) and 0 < key <= 0xFF and not key & 0x03, msg
            assert 50 <= msg["ms"] <= 2000 and 0 <= msg["gap"] <= 2000, msg
            pressed = self.i2c_ok and not self.refuse_next
            self.refuse_next = False
            if pressed:
                self.fan.press(self.ports[ch], key)
                self.executed.append(seq)
            self.clock.sleep((msg["ms"] + msg["gap"]) / 1000)
            answer = {"seq": seq, "ok": pressed, "i2c": self.i2c_ok}
            if self.i2c_ok:
                answer.update(in1=self.sense(1), in2=self.sense(2))
            if not pressed:
                answer["err"] = "i2c"
            if msg["key"] != vt.BEEP:  # beeps are not remembered, like Relay::finished
                self.answers.insert(0, answer)
                del self.answers[self.REMEMBER:]
        if self._lost("done"):
            return
        self.link.on_message("done", json.dumps(answer))


def make(fan=None, rj11=True, ports=("rj45", "rj11"), **kw):
    clock = Clock()
    fan = fan or tv.SimFan(clock=clock)
    relay = SimRelay(fan, clock, ports)
    link = vtboard.BoardLink("maxxfan/fan1/board", relay.receive, clock=clock,
                             wait=lambda cond, s: clock.sleep(s), first_seq=100)
    relay.boot(link)
    reports, online = {}, []
    worker = vt.VanTurtleFan(
        "fan1", vtboard.BoardChannel(link, 1), vtboard.BoardChannel(link, 2) if rj11 else None,
        post=lambda fn, *a: fn(*a), report=reports.__setitem__, set_online=online.append,
        sleep=clock.sleep, clock=clock, **kw)
    worker.init()
    return worker, relay, link, clock, reports, online


def run(worker, clock, max_errors=20):
    """converge(), with the worker thread's error handling: offline, wait 10 s, start again."""
    errors = 0
    for _ in range(400):
        try:
            if not worker.online:
                worker.init()
            if not worker.converge_step():
                return errors
        except OSError:
            errors += 1
            assert errors <= max_errors, "link never recovered"
            worker.online = False
            clock.sleep(10)
    raise AssertionError("did not converge")


def presses_of(relay):
    by_seq = {m["seq"]: m for m in relay.received}
    return [(by_seq[s]["ch"], by_seq[s]["key"]) for s in relay.executed]


def test_messages():
    worker, relay, link, clock, reports, online = make()
    assert online == [True] and reports == {"mode": 0}
    assert relay.received == [], "nothing may be pressed at start"
    worker.command("on", 1)
    run(worker, clock)
    assert relay.fan.on == 1
    m = relay.received
    assert [x["seq"] for x in m] == list(range(101, 101 + len(m))), "one new seq per press"
    assert m[0] == {"seq": 101, "ch": 1, "key": vt.BEEP, "ms": 150, "gap": 250}, "wake beep first"
    assert m[1]["ch"] == 2 and m[1]["key"] == vt.RJ11_OFF, "unknown on/off: RJ11 Off first"
    onoff = [x for x in m if x["key"] == vt.ONOFF]
    assert onoff == [{"seq": onoff[0]["seq"], "ch": 1, "key": vt.ONOFF, "ms": 750, "gap": 250}], m


def running(**kw):
    """A running fan whose speed the driver knows (10 % re-homes), wake beeps off."""
    worker, relay, link, clock, *_ = make(on_opens_lid=False, wake_beep=False, **kw)
    worker.command("on", 1)
    worker.command("speed", 10)
    run(worker, clock)
    assert relay.fan.speed == 1 and worker.belief["speed"] == 10
    return worker, relay, link, clock


def test_lost_answer_is_not_a_second_press():
    worker, relay, link, clock = running()
    before = len(relay.fan.presses)
    relay.drop = ["done"]
    worker.command("speed", relay.fan.speed * 10 + 10)
    assert run(worker, clock) == 0
    assert relay.received[-1]["seq"] == relay.received[-2]["seq"], "resent with the same seq"
    assert len(relay.fan.presses) == before + 1, "pressed once, answered twice"
    assert worker.belief["speed"] == relay.fan.speed * 10


def test_lost_press_is_sent_again():
    worker, relay, link, clock, *_ = make(wake_beep=False)
    relay.drop = ["press", "press"]
    worker.command("lid", 1)
    assert run(worker, clock) == 0
    assert relay.fan.lid == 1 and worker.belief["lid"] == 1
    lid_msgs = [m for m in relay.received if m["key"] == vt.RJ11_OPEN]
    assert len(lid_msgs) == 3 and len({m["seq"] for m in lid_msgs}) == 1
    assert presses_of(relay).count((2, vt.RJ11_OPEN)) == 1


def test_link_gives_up_and_retries_the_same_seq():
    """Pressed, then every answer lost until the link gives up. After the outage the worker
    wants the same key again; it goes out with the old seq, so the ESP32 only answers."""
    worker, relay, link, clock = running()
    worker.wake_beep = True
    speed = relay.fan.speed
    relay.drop = ["done", "press", "press"]
    worker.command("speed", speed * 10 + 10)
    assert run(worker, clock) == 1, "one outage"
    faster = [m for m in relay.received if m["key"] == vt.FASTER]
    assert len({m["seq"] for m in faster}) == 1, "same seq before and after the outage"
    assert relay.fan.speed == speed + 1 and worker.belief["speed"] == relay.fan.speed * 10
    beeps = [m for m in relay.received if m["key"] == vt.BEEP]
    assert len(beeps) == 1, "wake beep after the 10 s pause"


def test_board_offline_and_back():
    worker, relay, link, clock, reports, online = make()
    link.on_message("status", "offline", True)
    for call in (worker.poll, link.check):
        try:
            call()
            raise AssertionError("must raise while the board is offline")
        except OSError:
            pass
    link.on_message("status", "online", True)
    worker.poll()

    relay.heartbeat = False  # ESP32 hangs without its last will reaching the broker
    clock.sleep(40)
    try:
        worker.poll()
        raise AssertionError("must raise without a heartbeat")
    except OSError as e:
        assert "heartbeat" in str(e)
    relay.heartbeat = True
    relay.state()
    worker.poll()

    link.broker_lost()
    try:
        link.check()
        raise AssertionError("must raise without the broker")
    except OSError:
        pass
    link.on_message("status", "online", True)  # retained, comes back with the subscription
    link.check()


def test_bus_trouble_at_the_fan():
    worker, relay, link, clock, *_ = make(wake_beep=False)
    relay.i2c_ok = False
    relay.state()
    try:
        link.check()
        raise AssertionError("ESP32 reports it cannot reach the board")
    except OSError as e:
        assert "I2C" in str(e)

    relay.i2c_ok = True
    relay.state()
    worker.command("lid", 1)
    for fault in ("refuse_next", "i2c_ok"):  # the key write fails; or the whole bus, mid-press
        setattr(relay, fault, fault == "refuse_next")
        try:
            worker.converge_step()
            raise AssertionError("a press the ESP32 could not make must raise")
        except OSError as e:
            assert "did not press" in str(e), e
        assert relay.fan.presses == [] and worker.belief["lid"] is None
        relay.i2c_ok = True
        relay.state()
    assert run(worker, clock) == 0 and relay.fan.lid == 1


def test_auto_followed_from_heartbeat():
    worker, relay, link, clock, reports, _ = make()
    relay.fan.auto = 1  # pressed on the ceiling keypad
    clock.sleep(10)
    worker.poll()
    assert reports["mode"] == 1 and worker.belief["mode"] == 1
    worker.command("mode", 0)
    run(worker, clock)
    assert relay.fan.auto == 0 and worker.belief["mode"] == 0  # the card showed 0 at the touch


def test_ports_swapped():
    """RJ11 cable on port 1, RJ45 on port 2."""
    clock = Clock()
    fan = tv.SimFan(clock=clock)
    worker, relay, link, clock, *_ = make(fan, ports=("rj11", "rj45"))
    worker.rj45, worker.rj11 = vtboard.BoardChannel(link, 2), vtboard.BoardChannel(link, 1)
    relay.clock = clock
    worker.command("on", 1)
    worker.command("lid", 0)
    run(worker, clock)
    assert relay.fan.on == 1 and relay.fan.lid == 0


def test_random_lossy_link(seeds=60, steps=120):
    """Random commands over a link that loses a quarter of all messages. Outages happen
    (three losses in a row); after each, the fan must still match the belief."""
    outages = 0
    for seed in range(seeds):
        for rj11 in (True, False):
            rnd = random.Random(seed)
            clock = Clock()
            fan = tv.SimFan(on=1, speed=5, exhaust=1, lid=1, clock=clock, lid_travel_s=10.0)
            worker, relay, link, clock, *_ = make(fan, rj11=rj11, on_opens_lid=False,
                                                  rj11_off_closes_lid=False)
            relay.clock = fan.clock = clock
            fan.clock = clock
            worker.belief.update(on=1, speed=50, dir=1, lid=1)
            relay.loss = (rnd, 0.25)
            target = [1, 1, 50, 1]
            for _ in range(steps):
                i = rnd.randrange(4)
                target[i] = rnd.choice((10, 20, 50, 90, 100)) if i == 2 else rnd.randrange(2)
                worker.command(("on", "lid", "speed", "dir")[i], target[i])
                if rnd.random() < 0.6:
                    outages += run(worker, clock, max_errors=60)
                    tv.check(fan, worker, tuple(target), check_dir=True)
                clock.sleep(rnd.choice((0.5, 3, 20)))
            outages += run(worker, clock, max_errors=60)
            tv.check(fan, worker, tuple(target), check_dir=True)
            keys = [s for s in relay.executed if next(
                m for m in relay.received if m["seq"] == s)["key"] != vt.BEEP]
            assert len(keys) == len(set(keys)), "a seq was pressed twice"
            assert fan.reversals == 0, (seed, "lid keyed while travelling")
    assert outages > 50, "the test should exercise outages (%d)" % outages
    return outages


def test_link_errors():
    link = vtboard.BoardLink("p", lambda *a: None)
    for bad in (0, 3):
        try:
            vtboard.BoardChannel(link, bad)
            raise AssertionError("port %r accepted" % bad)
        except ValueError:
            pass
    link.on_message("state", "not json")
    link.on_message("state", "[1, 2]")
    link.on_message("state", '{"in1": 999, "i2c": true}')
    assert link.inputs[1] == 0xFF and link.i2c is True


def test_driver_integration():
    from test_driver import load_driver
    d = load_driver()
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    cfg.read_string("[fan1]\nname = Galley fan\nbackend = vanturtle-esp32\nlid_settle_s = 15\n"
                    "[fan2]\nbackend = vanturtle-esp32\ntopic = van/fan2/  ; trailing slash\n"
                    "rj45 = 2\nrj11 = 1\n"
                    "[bad1]\nbackend = vanturtle-esp32\nrj45 = 3\n"
                    "[bad2]\nbackend = vanturtle-esp32\nrj11 = 1\n")
    sent, posted = [], []
    client = types.SimpleNamespace(publish=lambda t, p, qos=1: sent.append((t, p, qos)),
                                   subscribe=lambda topics: sent.append(("SUB", topics, 0)))
    links = {}
    bridge = d.Bridge({}, client, links)
    post = lambda fn, *a: posted.append((fn, a))  # noqa: E731
    fan, worker, link = d.make_vtboard_fan("fan1", cfg, None, 60, bridge.publish_raw, post=post)
    fan2, worker2, link2 = d.make_vtboard_fan("fan2", cfg, None, 61, bridge.publish_raw, post=post)
    worker.state_file = worker2.state_file = None
    for section in ("bad1", "bad2"):
        try:
            d.make_vtboard_fan(section, cfg, None, 62, bridge.publish_raw)
            raise AssertionError(section + " accepted")
        except ValueError:
            pass
    d.add_prefix(links, link.prefix, link)
    d.add_prefix(links, link2.prefix, link2)
    try:
        d.add_prefix(links, "maxxfan/fan1/board/x", link)
        raise AssertionError("overlapping prefix accepted")
    except ValueError:
        pass

    svc, out = fan.svc, "/SwitchableOutput/"
    assert link.prefix == "maxxfan/fan1/board" and link2.prefix == "van/fan2"
    assert (worker.rj45.number, worker.rj11) == (1, None)
    assert (worker2.rj45.number, worker2.rj11.number) == (2, 1)
    assert worker.lid_settle_s == 15 and worker.on_opens_lid is None
    assert svc["/Mgmt/Connection"] == "VanTurtle board via WiFi, maxxfan/fan1/board"
    assert not any("setpoint" in p for p in svc.paths), "no setpoint on VanTurtle fans"
    bridge._on_connect(client)
    topics = sent.pop()[1]
    assert ("maxxfan/fan1/board/#", 1) in topics and ("van/fan2/#", 1) in topics

    # Status and state reach the right link; the worker comes online.
    bridge.dispatch("maxxfan/fan1/board/status", "online", True)
    bridge.dispatch("maxxfan/fan1/board/state", '{"in1": 1, "in2": 255, "i2c": true}', True)
    bridge.dispatch("van/fan2/status", "offline", True)
    worker.init()
    for fn, a in posted:
        fn(*a)
    posted.clear()
    assert svc["/Connected"] == 1 and fan2.svc["/Connected"] == 0
    try:
        worker2.init()
        raise AssertionError("fan 2's board is offline")
    except OSError:
        pass

    # A touch shows at once; the press goes out with qos 0 and returns when answered.
    assert svc.gui_write(out + "lid/State", 1) is True
    assert svc[out + "lid/State"] == 1 and worker.desired["lid"] == 1
    link.wait = lambda cond, s: bridge.dispatch(
        "maxxfan/fan1/board/done", json.dumps({"seq": link.pending, "ok": True, "i2c": True,
                                               "in1": 1, "in2": 255}))
    worker.wake_beep = False
    assert worker.converge_step() is True
    topic, payload, qos = sent[-1]
    assert topic == "maxxfan/fan1/board/press" and qos == 0, sent[-1]
    assert json.loads(payload)["key"] == vt.LID_TOGGLE and worker.belief["lid"] == 1
    bridge._all_offline()
    try:
        link.check()
        raise AssertionError("broker gone: the link must report it")
    except OSError:
        pass
    print("vtboard: driver integration passed")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and k != "test_driver_integration"]
    for test in tests:
        result = test()
        if test is test_random_lossy_link:
            print("vtboard: random lossy link passed (%d outages survived)" % result)
    test_driver_integration()
    print("vtboard: all %d checks passed" % (len(tests) + 1))


if __name__ == "__main__":
    main()
