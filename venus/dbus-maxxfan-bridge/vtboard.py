"""VanTurtle board at the fan, behind an ESP32 that relays key presses over MQTT (option E).

The board and the fan are the same as in option V, so vanturtle.VanTurtleFan drives them
unchanged: same belief/desired model, same key timings. Only the transport differs. Instead
of writing to /dev/i2c, each key press is one MQTT message to the ESP32 next to the board,
which holds the key, releases it, waits the gap, reads the board's inputs and answers.
Firmware: archive/firmware/vanturtle-board.yaml. Topics under <prefix> (default maxxfan/<fan>/board):

  press   driver -> ESP32  {"seq":17,"ch":1,"key":16,"ms":750,"gap":250}
  done    ESP32 -> driver  {"seq":17,"ok":true,"i2c":true,"in1":255,"in2":255}
                           ok: the key went down and up again (else "err"); i2c: inputs read
  state   ESP32 -> driver  {"in1":255,"in2":255,"i2c":true}, retained, every 10 s and on change
  status  ESP32 -> driver  online / offline (retained birth message and last will)

A press whose answer does not come is sent again with the same seq. The ESP32 remembers the
answers to its last few presses and repeats the answer instead of pressing again, so a lost
answer never becomes a second press. A press still unanswered when the link gives up is
retried with the same seq the next time the driver wants the same key. Beeps are the
exception on both sides: a second beep does no harm, so the ESP32 does not remember them and
they cannot push a real key out of its memory, however many outages come in a row.
"""

import json
import logging
import random
import threading
import time

log = logging.getLogger("dbus-maxxfan-bridge")

BEEP = 0x80  # harmless twice; pressed before a burst after a quiet spell (vanturtle.py)


class BoardLink:
    """The ESP32 beside one fan's VanTurtle board.

    on_message, broker_lost and tick are called on the GLib main loop (Bridge); press, check
    and auto_on on the fan's worker thread. publish(topic, payload) must be thread-safe.
    """

    def __init__(self, prefix, publish, answer_s=2.0, tries=3, stale_s=35.0,
                 clock=time.monotonic, wait=None, first_seq=None):
        self.prefix, self.publish = prefix, publish
        self.answer_s, self.tries, self.stale_s = answer_s, tries, stale_s
        self.clock = clock
        self.wait = wait or (lambda cond, seconds: cond.wait(seconds))
        self.cond = threading.Condition()
        self.status = None  # retained birth / last will: "online" or "offline"
        self.i2c = False  # the ESP32 can talk to the board
        self.inputs = {1: 0xFF, 2: 0xFF}  # input registers of the board's two ports
        self.seen = None  # clock() of the last state or answer from the ESP32
        self.seq = first_seq if first_seq is not None else random.randint(1, 1 << 30)
        self.pending = None  # seq waiting for its answer
        self.answer = None
        self.unanswered = None  # ((ch, key, ms), seq) of a key press that never got an answer

    def __repr__(self):
        return self.prefix

    # ---- main loop ----------------------------------------------------------

    def on_message(self, leaf, payload, retained=False):
        with self.cond:
            if leaf == "status":
                self.status = payload
                self.cond.notify_all()
                return
            if leaf not in ("state", "done"):
                return
            try:
                data = json.loads(payload)
            except ValueError:
                log.warning("%s/%s: not JSON: %r", self.prefix, leaf, payload[:80])
                return
            if not isinstance(data, dict):
                return
            self.seen = self.clock()
            for n in (1, 2):
                value = data.get("in%d" % n)
                if isinstance(value, int) and 0 <= value <= 0xFF:
                    self.inputs[n] = value
            if leaf == "state" or "i2c" in data:
                self.i2c = data.get("i2c") is True
            if leaf == "done" and self.pending is not None and data.get("seq") == self.pending:
                self.answer = data
                self.cond.notify_all()

    def broker_lost(self):
        with self.cond:
            self.status = None
            self.cond.notify_all()

    def tick(self):
        pass

    # ---- worker thread --------------------------------------------------------

    def _problem(self):
        if self.status != "online":
            return "board offline" if self.status else "no word from the board"
        if self.seen is None or self.clock() - self.seen > self.stale_s:
            return "no heartbeat from the board for %d s" % self.stale_s
        if not self.i2c:
            return "the ESP32 cannot reach the VanTurtle board (I2C)"
        return None

    def check(self):
        with self.cond:
            problem = self._problem()
        if problem:
            raise OSError(problem)

    def auto_on(self, channel):
        with self.cond:
            problem = self._problem()
            value = self.inputs[channel]
        if problem:
            raise OSError(problem)
        return not value & 0x01  # 0 means auto is on

    def reset(self):
        pass  # the worker calls bus.reset() after an error; nothing to reset here

    def press(self, channel, key, hold, gap):
        ms, gap_ms = int(round(hold * 1000)), int(round(gap * 1000))
        self.check()
        what = (channel, key, ms)
        with self.cond:
            seq = None
            if self.unanswered and self.unanswered[0] == what:
                seq = self.unanswered[1]  # same key again: if it was pressed, the ESP32 only answers
            if seq is None:
                self.seq = self.seq % (1 << 30) + 1
                seq = self.seq
            self.pending, self.answer = seq, None
        message = json.dumps({"seq": seq, "ch": channel, "key": key, "ms": ms, "gap": gap_ms},
                             separators=(",", ":"))
        answer = None
        try:
            for _ in range(self.tries):
                self.publish(self.prefix + "/press", message)
                answer = self._await(hold + gap + self.answer_s)
                if answer is not None:
                    break
        finally:
            with self.cond:
                self.pending = None
                if key != BEEP:  # a wake beep in between changes nothing; other keys replace it
                    self.unanswered = (what, seq) if answer is None else None
        if answer is None:
            raise OSError("no answer from the board")
        if answer.get("ok") is not True:
            raise OSError("the board did not press: %s" % answer.get("err", "unknown error"))

    def _await(self, timeout):
        deadline = self.clock() + timeout
        with self.cond:
            while self.answer is None:
                left = deadline - self.clock()
                if self.status != "online" or left <= 0:
                    return None
                self.wait(self.cond, left)
            return self.answer


class BoardChannel:
    """One port of the board at the fan, with the interface of vanturtle.Channel."""

    def __init__(self, link, number):
        if number not in (1, 2):
            raise ValueError("board port must be 1 or 2, not %r" % number)
        self.link, self.number = link, number
        self.bus = link  # the worker resets channel.bus after an error

    def __repr__(self):
        return "%s port %d" % (self.link.prefix, self.number)

    def init(self):
        self.link.check()  # the ESP32 prepares the board itself at start-up

    def press(self, key, hold, gap, _sleep):
        self.link.press(self.number, key, hold, gap)

    def auto_on(self):
        return self.link.auto_on(self.number)
