"""VanTurtle Smart Controller with VanTurtle's WiFi firmware, over MQTT (hardware option W).

The controller sits in the fan, presses the fan's keys through the RJ45 wall-control jack and
measures the fan's current. Its MQTT interface has one topic per field, used in both
directions: it publishes its state there (retained, QoS 1) and acts on what others publish
there. The topics are typed into the controller's web page, all under one prefix
(hardware/vanturtle-smart-controller.md):

  <prefix>/on     0/1     state and command   fan running, sensed by the controller
  <prefix>/speed  1..10   state and command
  <prefix>/dir    0/1     state and command   the controller's own guess; may be a toggle
  <prefix>/auto   0/1     state and command   auto mode, sensed; may be a toggle
  <prefix>/lid    any     command only        toggles the lid; nothing reports its position
  <prefix>/alive  1       state only          every 60 s

Consequences handled here:
- The driver hears its own commands back on the same topics; those echoes are dropped.
- The controller ignores everything it receives for a moment after each of its own publishes
  ("echo suppress"). So commands go out one at a time, and only after the controller has been
  quiet for quiet_s.
- A touch becomes a *wish*, shown on screen until the controller reports that value. Without
  a report within confirm_s, on/off and speed are sent once more; after that the wish is
  dropped and the screen shows the last report again. Direction, lid and Auto are never
  repeated: they are, or may be, toggles (VanTurtle's web app toggles Auto), and a repeat
  would undo the first. Wishes are never re-sent after a report, so the driver does not
  fight the keypad or the remote.
- Direction: VanTurtle says "0 = maybe forward, 1 = maybe reverse". The driver takes 0 as
  intake and 1 as exhaust; dir_swapped (swap_direction in config.ini) turns that round.
- The lid is a belief, kept in the state file; on the very first start it is assumed closed.
  It is toggled only when the wish differs from the belief, and never sooner than
  lid_settle_s after the last lid movement.
- Online means a live (not retained) message arrived within alive_timeout_s.

Everything runs on the D-Bus main loop: the driver calls on_message() for each MQTT message,
command() for each GUI touch and tick() once a second.
"""

import json
import logging
import os
import time

log = logging.getLogger("dbus-maxxfan-bridge")

LEAF = {"on": "on", "speed": "speed", "dir": "dir", "mode": "auto"}  # driver key -> topic leaf
KEY = {leaf: key for key, leaf in LEAF.items()}
ORDER = ("mode", "on", "lid", "dir", "speed")  # leave Auto first; speed and direction last
RESENDABLE = ("on", "speed")  # absolute: sending twice is harmless. Auto may be a toggle
TRUE = ("1", "true", "on", "yes")
FALSE = ("0", "false", "off", "no")


def parse(key, payload):
    """Controller payload -> driver value (speed in %), or None if it makes no sense."""
    text = payload.strip().lower()
    if key != "speed":
        if text in TRUE:
            return 1
        if text in FALSE:
            return 0
    try:
        number = float(text)
    except ValueError:
        return None
    if number != int(number):
        return None
    number = int(number)
    if key == "speed":
        return number * 10 if 1 <= number <= 10 else None
    return number if number in (0, 1) else None


def encode(key, value):
    return str(value // 10) if key == "speed" else str(int(value))


class VtWifiFan:
    def __init__(self, fan_id, prefix, publish, report, set_online, state_file=None,
                 on_opens_lid=None, lid_settle_s=12.0, confirm_s=10.0, quiet_s=2.0,
                 alive_timeout_s=150.0, echo_s=5.0, dir_swapped=False, clock=time.monotonic):
        self.id, self.prefix = fan_id, prefix.rstrip("/")
        self._publish, self.report, self._set_online = publish, report, set_online
        self.state_file = state_file
        self.on_opens_lid = on_opens_lid  # True / False / None = not known yet
        self.lid_settle_s, self.confirm_s, self.quiet_s = lid_settle_s, confirm_s, quiet_s
        self.alive_timeout_s, self.echo_s = alive_timeout_s, echo_s
        self.dir_swapped = dir_swapped  # controller's dir 0 means exhaust
        self.clock = clock

        self.reported = dict.fromkeys(LEAF)  # last value the controller published
        self.wish = {}  # key -> value the user asked for and the fan has not confirmed yet
        self.inflight = None  # [key, value, deadline, resends left] of the command sent last
        self.echoes = {}  # leaf -> [[payload, expiry], ...] for our own publishes
        self.lid = 0  # belief: 1 open, 0 closed. First start: assumed closed (SETUP.md)
        self.last_lid_motion = None
        self.last_live = None  # last message from the controller (not our echo)
        self.last_sent = None
        self.online = False
        self._load()

    def __repr__(self):
        return "VtWifiFan(%s, %s)" % (self.id, self.prefix)

    # ---- MQTT -> fan -------------------------------------------------------

    def on_message(self, leaf, payload, retained=False):
        now = self.clock()
        if not retained:
            if self._is_echo(leaf, payload, now):
                return
            self.last_live = now
            if not self.online:
                self.online = True
                self._set_online(True)
                self._show_all()
                log.info("%s: controller online at %s", self.id, self.prefix)
        key = KEY.get(leaf)
        if key is None:
            return  # alive, voltage, current, power, anything else
        value = parse(key, payload)
        if value is None:
            log.warning("%s: bad payload %r on %s/%s", self.id, payload, self.prefix, leaf)
            return
        if key == "dir" and self.dir_swapped:
            value = 1 - value
        old = self.reported[key]
        self.reported[key] = value
        if not retained and old == 0 and value == 1:
            self._started(key, now)
        if self.inflight and self.inflight[0] == key and self.inflight[1] == value:
            self.inflight = None  # confirmed
        if self.wish.get(key) == value and not (self.inflight and self.inflight[0] == key):
            del self.wish[key]
        if key not in self.wish:
            self.report(key, value)

    def _started(self, key, now):
        """The fan started or entered Auto. Auto starts the fan and opens the lid; switching on
        opens it when on_opens_lid says so. Either way the lid may be moving now."""
        if key == "on" and self.on_opens_lid is not True:
            if self.on_opens_lid is None:
                self.last_lid_motion = now
            return
        if key in ("on", "mode"):
            self.last_lid_motion = now
            if self.lid != 1:
                self.lid = 1
                self._save()
                if "lid" not in self.wish:
                    self.report("lid", 1)

    def broker_lost(self):
        self._go_offline("MQTT broker connection lost")

    # ---- GUI -> fan --------------------------------------------------------

    def command(self, key, value):
        value = int(value)
        if key == "mode" and value == 1:
            for other in [k for k in self.wish if k != "mode"]:
                del self.wish[other]  # the fan's thermostat takes over
                self._show(other)
        elif key != "mode" and self.wish.get("mode", self.reported["mode"]) == 1:
            self.wish["mode"] = 0  # touching a manual control leaves Auto first
            self.report("mode", 0)
        self.wish[key] = value
        self.report(key, value)
        self._pump(self.clock())

    # ---- sending, one command at a time ------------------------------------

    def _pump(self, now):
        if not self.online:
            return
        quiet = all(t is None or now - t >= self.quiet_s for t in (self.last_live, self.last_sent))
        if self.inflight:
            key, value, deadline, resends = self.inflight
            if now < deadline:
                return
            still_wanted = self.wish.get(key) == value  # not replaced or cancelled meanwhile
            if resends and still_wanted:
                if quiet:
                    log.info("%s: no confirmation of %s=%s, sending again", self.id, key, value)
                    self._publish_leaf(LEAF[key], self._encode(key, value), now)
                    self.inflight = [key, value, now + self.confirm_s, resends - 1]
                return
            self.inflight = None
            if still_wanted:
                log.warning("%s: controller did not confirm %s=%s", self.id, key, value)
                del self.wish[key]
                self._show(key)
        if self.reported["mode"] == 1 and "mode" not in self.wish:
            for key in list(self.wish):  # Auto could not be left: manual keys would do nothing
                del self.wish[key]
                self._show(key)
        if not quiet:
            return
        for key in ORDER:
            if key not in self.wish:
                continue
            target = self.wish[key]
            if key == "lid":
                if target == self.lid:
                    del self.wish[key]
                    continue
                if self.last_lid_motion is not None and now - self.last_lid_motion < self.lid_settle_s:
                    continue  # still travelling; try again on a later tick
                self._publish_leaf("lid", "1", now)  # any value toggles the lid
                self.lid, self.last_lid_motion = target, now
                del self.wish[key]
                self._save()
                return
            if target == self.reported[key]:
                del self.wish[key]
                continue
            self._publish_leaf(LEAF[key], self._encode(key, target), now)
            self.inflight = [key, target, now + self.confirm_s, 1 if key in RESENDABLE else 0]
            if key == "on" and target == 1 and self.on_opens_lid is not False:
                self.last_lid_motion = now
            return

    def _encode(self, key, value):
        if key == "dir" and self.dir_swapped:
            value = 1 - value
        return encode(key, value)

    def _publish_leaf(self, leaf, payload, now):
        self.echoes.setdefault(leaf, []).append([payload, now + self.echo_s])
        self.last_sent = now
        self._publish("%s/%s" % (self.prefix, leaf), payload)

    def _is_echo(self, leaf, payload, now):
        waiting = [e for e in self.echoes.get(leaf, ()) if e[1] > now]
        for i, (sent, _expiry) in enumerate(waiting):
            if sent == payload.strip():
                del waiting[i]
                self.echoes[leaf] = waiting
                return True
        self.echoes[leaf] = waiting
        return False

    # ---- once a second -----------------------------------------------------

    def tick(self):
        now = self.clock()
        if self.online and now - self.last_live > self.alive_timeout_s:
            self._go_offline("no keepalive for %d s" % self.alive_timeout_s)
        self._pump(now)

    def _go_offline(self, why):
        if not self.online:
            return
        self.online = False
        self.inflight = None
        wished = list(self.wish)
        self.wish.clear()
        for key in wished:
            self._show(key)
        self._set_online(False)
        log.warning("%s: controller offline (%s)", self.id, why)

    def _show(self, key):
        value = self.lid if key == "lid" else self.reported.get(key)
        if value is not None:
            self.report(key, value)

    def _show_all(self):
        for key in ORDER:
            if key not in self.wish:
                self._show(key)

    # ---- persistence: only the lid is ours to remember -------------------------

    def _load(self):
        if not self.state_file:
            return
        try:
            with open(self.state_file) as f:
                saved = json.load(f)
            if saved.get("lid") in (0, 1):
                self.lid = saved["lid"]
        except (OSError, ValueError):
            pass

    def _save(self):
        if not self.state_file:
            return
        try:
            tmp = self.state_file + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"lid": self.lid}, f)
            os.replace(tmp, self.state_file)
        except OSError as e:
            log.warning("%s: cannot save state: %s", self.id, e)
