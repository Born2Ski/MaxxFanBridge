"""Checks that test_vanturtle.py actually catches mistakes: each case breaks the driver on
purpose and expects a test to fail.

    python3 tests/mutation_check.py
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_vanturtle as t  # noqa: E402
import test_vtwifi as w  # noqa: E402
import test_package as tk  # noqa: E402
import plugin_api  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.path.join(ROOT, "gui-plugin", "MaxxFanBridge")
MUTANT_DIR = os.path.join(ROOT, ".build", "test-tmp", "plugin-mutant", "MaxxFanBridge")


def plugin_copy(name, qml, old, new):
    """The plugin with one planted bug, in .build; fails loudly if the text no longer matches."""
    shutil.rmtree(MUTANT_DIR, ignore_errors=True)
    shutil.copytree(PLUGIN_DIR, MUTANT_DIR)
    path = os.path.join(MUTANT_DIR, qml)
    with open(path) as f:
        text = f.read()
    assert text.count(old) == 1, "plugin mutant %r: text not found once in %s" % (name, qml)
    with open(path, "w") as f:
        f.write(text.replace(old, new))
    return MUTANT_DIR


def run_plugin_api(name, qml, old, new):
    """A planted bug that gui-v2's API list must catch (tests/plugin_api.py)."""
    try:
        plugin_api.check_api_use(plugin_copy(name, qml, old, new))
    except AssertionError as e:
        print("caught:     %-32s %s" % (name, str(e).splitlines()[0][:60]))
        return True
    print("NOT CAUGHT: " + name)
    return False


def run_plugin(name, qml, old, new):
    """A planted bug in the plugin's behaviour, run by tests/test_plugin.py in its own process
    (it needs PySide6). Without PySide6 it cannot run; that is reported, not counted."""
    env = dict(os.environ, MAXXFAN_PLUGIN_DIR=plugin_copy(name, qml, old, new))
    result = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "test_plugin.py")], env=env,
                            capture_output=True, text=True)
    if "skipped" in result.stdout:
        print("not run:    %-32s (no PySide6)" % name)
        return True
    if result.returncode != 0:
        last = [line for line in result.stderr.splitlines() if line.startswith("AssertionError")]
        print("caught:     %-32s %s" % (name, (last[-1] if last else "fails")[:60]))
        return True
    print("NOT CAUGHT: " + name)
    return False
import test_presets as tp  # noqa: E402
import test_vtboard as tb  # noqa: E402


def run(name, patch, test):
    vt = importlib.reload(t.vt)
    t.vt = vt
    patch(vt)
    try:
        test()
    except AssertionError as e:
        print("caught:     %-32s %s" % (name, str(e)[:60]))
        return True
    print("NOT CAUGHT: " + name)
    return False


def with_kw(**over):
    def patch(vt):
        orig = vt.VanTurtleFan.__init__

        def init(self, *a, **k):
            k.update(over)
            orig(self, *a, **k)
        vt.VanTurtleFan.__init__ = init
    return patch


def lid_kept(vt):
    vt.VanTurtleFan._lid_after_rj11_off = lambda self, want, b: self._update(on=0)


def no_reassert(vt):
    def command(self, key, value):
        with self.lock:
            self.desired[key] = int(value)
        self.wake.set()
    vt.VanTurtleFan.command = command


def no_speed_rehome(vt):
    orig = vt.VanTurtleFan.command

    def command(self, key, value):
        orig(self, key, value)
        if key == "speed" and self.belief["speed"] is None:
            self.belief["speed"] = 30  # pretend the old belief survived
    vt.VanTurtleFan.command = command


def config_first(vt):
    def init(self):
        self.bus.write(self.address, self.reg_cfg, 0x01)
        self.bus.write(self.address, self.reg_out, 0x00)
    vt.Channel.init = init


def auto_assumed_off(vt):
    def after(self, mode):
        self.belief["on"] = self.belief["lid"] = 0
    vt.VanTurtleFan._after_auto_change = after


def run_w(name, patch, test):
    """The same for the VanTurtle WiFi backend (test_vtwifi.py)."""
    vw = importlib.reload(w.vtwifi)
    w.vtwifi = vw
    patch(vw)
    try:
        test()
    except AssertionError as e:
        print("caught:     %-32s %s" % (name, str(e)[:60]))
        return True
    print("NOT CAUGHT: " + name)
    return False


def w_kw(**over):
    def patch(vw):
        orig = vw.VtWifiFan.__init__

        def init(self, *a, **k):
            k.update(over)
            orig(self, *a, **k)
        vw.VtWifiFan.__init__ = init
    return patch


def w_no_echo_filter(vw):
    vw.VtWifiFan._is_echo = lambda self, leaf, payload, now: False


def w_resend_toggles(vw):
    vw.RESENDABLE = ("on", "speed", "mode", "dir")


def w_resend_auto(vw):
    vw.RESENDABLE = ("on", "speed", "mode")


def w_lid_unknown_at_start(vw):
    orig = vw.VtWifiFan.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        if not self.state_file:
            self.lid = None
    vw.VtWifiFan.__init__ = init


def w_retained_is_alive(vw):
    orig = vw.VtWifiFan.on_message
    vw.VtWifiFan.on_message = lambda self, leaf, payload, retained=False: orig(self, leaf, payload, False)


def w_auto_not_left(vw):
    orig = vw.VtWifiFan.command

    def command(self, key, value):
        saved = self.reported["mode"]
        if key != "mode":
            self.reported["mode"] = 0  # forget that the fan is in Auto while handling the touch
        try:
            orig(self, key, value)
        finally:
            self.reported["mode"] = saved
    vw.VtWifiFan.command = command


def w_auto_keeps_wishes(vw):
    orig = vw.VtWifiFan.command

    def command(self, key, value):
        kept = dict(self.wish)
        orig(self, key, value)
        if key == "mode" and int(value) == 1:
            kept.update(self.wish)
            self.wish = kept
    vw.VtWifiFan.command = command


def run_p(name, attr, value, test, owner=None):
    """The same for presets: replace one attribute of the driver for the duration of a test."""
    owner = owner or tp.d
    orig = getattr(owner, attr)
    setattr(owner, attr, value(orig) if callable(value) else value)
    try:
        test()
    except AssertionError as e:
        print("caught:     %-32s %s" % (name, str(e)[:60]))
        return True
    finally:
        setattr(owner, attr, orig)
    print("NOT CAUGHT: " + name)
    return False


def run_e(name, patch, test):
    """The same for option E's link to the ESP32 (vtboard.py)."""
    importlib.reload(t.vt)  # undo the last vanturtle mutant: option E runs on that code too
    vb = importlib.reload(tb.vtboard)
    patch(vb)
    try:
        test()
    except AssertionError as e:
        print("caught:     %-32s %s" % (name, str(e)[:60]))
        return True
    finally:
        importlib.reload(tb.vtboard)
    print("NOT CAUGHT: " + name)
    return False


def e_kw(**over):
    def patch(vb):
        orig = vb.BoardLink.__init__

        def init(self, *a, **k):
            k.update(over)
            orig(self, *a, **k)
        vb.BoardLink.__init__ = init
    return patch


def e_source(old, new):
    """Mutate vtboard.py's source text and load it in place of the module's contents."""
    def patch(vb):
        text = open(vb.__file__).read()
        assert text.count(old) == 1, "mutant no longer matches vtboard.py: " + old
        exec(compile(text.replace(old, new), vb.__file__, "exec"), vb.__dict__)
    return patch


e_forget_unanswered = e_source("seq = self.unanswered[1]", "seq = None")


def e_wrap_messages(change):
    def patch(vb):
        orig = vb.BoardLink.on_message

        def on_message(self, leaf, payload, retained=False):
            return orig(self, leaf, change(leaf, payload), retained)
        vb.BoardLink.on_message = on_message
    return patch


def e_refusal_as_pressed(leaf, payload):
    return payload.replace('"ok": false', '"ok": true') if leaf == "done" else payload


def e_status_ignored(leaf, payload):
    return "online" if leaf == "status" else payload


def e_beep_like_any_key(vb):
    vb.BEEP = -1


def main():
    seq = lambda: [t.test_random_sequences(True, True, True, s) for s in range(5)]  # noqa: E731
    results = [
        run("homing with only 5 presses", with_kw(homing_presses=5), t.test_all_starts_both_ports),
        run("no wake beep", with_kw(wake_beep=False), t.test_all_starts_both_ports),
        run("assume RJ11 Off keeps the lid", lid_kept, seq),
        run("no re-assert on each touch", no_reassert, t.test_keypad_drift),
        run("config register before outputs", config_first, t.test_init_order_and_release),
        run("no re-home at 10 %", no_speed_rehome, t.test_keypad_drift),
        run("wrong belief after Auto", auto_assumed_off, t.test_auto_mode),
        run("ignore on_opens_lid", with_kw(on_opens_lid=False),
            lambda: t.test_random_sequences(False, False, True, 0)),
        run("no wait for the lid stroke", with_kw(lid_settle_s=0.0), t.test_lid_settle),
        run("lid stroke wait too short", with_kw(lid_settle_s=5.0), t.test_lid_settle),
    ]
    results += [
        run_w("WiFi: own echo taken as confirmation", w_no_echo_filter, w.test_own_echo_is_not_a_confirmation),
        run_w("WiFi: toggles resent", w_resend_toggles, w.test_toggles_are_never_repeated),
        run_w("WiFi: no quiet gap before sending", w_kw(quiet_s=0.0), w.test_one_command_at_a_time_after_quiet),
        run_w("WiFi: no wait for the lid stroke", w_kw(lid_settle_s=0.0), w.test_lid_belief_settle_and_persistence),
        run_w("WiFi: retained counts as alive", w_retained_is_alive, w.test_start_retained_then_live),
        run_w("WiFi: Auto not left first", w_auto_not_left, w.test_one_command_at_a_time_after_quiet),
        run_w("WiFi: Auto keeps manual wishes", w_auto_keeps_wishes, w.test_selecting_auto_drops_manual_wishes),
        run_w("WiFi: ignore on_opens_lid", w_kw(on_opens_lid=False), w.test_on_opens_lid),
        run_w("WiFi: Auto resent", w_resend_auto, w.test_auto_is_never_repeated),
        run_w("WiFi: swap_direction ignored", w_kw(dir_swapped=False), w.test_swap_direction),
        run_w("WiFi: lid unknown at first start", w_lid_unknown_at_start, w.test_first_start_assumes_lid_closed),
    ]
    results += [
        run_p("presets: speed before leaving Auto", "PRESET_ORDER", ("fan", "lid", "direction", "speed", "mode"),
              tp.test_auto_and_offline),
        run_p("presets: touch does not darken", "_touched", lambda orig: (lambda self, fan_id: None),
              tp.test_card_and_apply, owner=tp.d.Presets),
        run_p("closing the lid leaves the fan on", "_stop_before_closing", lambda orig: (lambda self: None),
              tp.test_closing_the_lid_stops_the_fan, owner=tp.d.Fan),
        run_p("forget: other devices' settings too", "ours", lambda orig: (lambda items: sorted(map(str, items))),
              tk.test_forget, owner=tk.forget),
        run_p("forget: config.ini kept", "FILES", ("presets.json", "state-*.json", "*.tmp"),
              tk.test_forget, owner=tk.forget),
        run_p("presets: save stores every preset", "_store",
              lambda orig: (lambda self, key: [orig(self, k) for k in self.order]),
              tp.test_save_as, owner=tp.d.Presets),
    ]
    card, page = "MaxxFanBridge_Card.qml", "MaxxFanBridge_Fan.qml"
    results += [
        run_plugin_api("plugin: member gui-v2 lacks", card, "secondaryText: root.fanAt(0)", "subText: root.fanAt(0)"),
        run_plugin_api("plugin: card row not flat", card, 'objectName: "fanRow0"\n\t\tflat: true', 'objectName: "fanRow0"'),
        run_plugin_api("plugin: imports gui-v2 internals", page, "import QtQuick\n",
                       "import QtQuick\nimport Victron.VenusOS\n"),
        run_plugin("plugin: active preset not shown", card, "return preset.key", 'return ""'),
        run_plugin("plugin: icons usable with no fan", card, "enabled: root.anyFanConnected", "enabled: true"),
        run_plugin("plugin: Aangepast opens nothing", card, "onTapped: allFans.click()", "onTapped: {}"),
        run_plugin("plugin: tap sends nothing", card, "chooser.setValue(1)", "chooser.setValue(0)"),
        run_plugin("plugin: page usable when offline", page, 'dataItem.uid: root.out("fan", "State")\n\t\t\tinteractive: root.connected',
                   'dataItem.uid: root.out("fan", "State")\n\t\t\tinteractive: true'),
    ]
    results += [
        run_e("board: no resend", e_kw(tries=1), tb.test_lost_press_is_sent_again),
        run_e("board: unanswered seq not reused", e_forget_unanswered, tb.test_link_gives_up_and_retries_the_same_seq),
        run_e("board: beep replaces unanswered key", e_beep_like_any_key,
              tb.test_link_gives_up_and_retries_the_same_seq),
        run_e("board: heartbeat not checked", e_kw(stale_s=1e9), tb.test_board_offline_and_back),
        run_e("board: last will ignored", e_wrap_messages(e_status_ignored), tb.test_board_offline_and_back),
        run_e("board: refusal taken as pressed", e_wrap_messages(e_refusal_as_pressed), tb.test_bus_trouble_at_the_fan),
        run_e("board: unanswered forgotten (random)", e_forget_unanswered, lambda: tb.test_random_lossy_link(seeds=15)),
    ]
    clean_e = not run_e("board: unbroken (must NOT be caught)", lambda vb: None,
                        lambda: [f() for k, f in sorted(vars(tb).items()) if k.startswith("test_")])
    clean_p = clean_e and not run_p("presets: unbroken (must NOT be caught)", "PRESET_SETTLE_S", 60, tp.main)
    clean = clean_w = clean_p and not run_w("WiFi: unbroken (must NOT be caught)", lambda vw: None, w.main)
    importlib.reload(w.vtwifi)
    clean = clean_w and not run("unbroken driver (must NOT be caught)", lambda vt: None,
                    lambda: (t.test_all_starts_both_ports(), seq(), t.test_keypad_drift(), t.test_auto_mode(),
                             t.test_lid_settle()))
    importlib.reload(t.vt)
    # every mutation caught, and the unbroken driver passes
    ok = all(results) and clean
    print("mutation check:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
