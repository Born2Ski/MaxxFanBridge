"""Checks the gui-v2 plugin (gui-plugin/MaxxFanBridge) against gui-v2's own list of the
Victron.GuiPlugins API (tests/plugin_stubs/guiplugins-api.json, from gui-v2 v1.4.6), and against
the plugin rules a desktop can check. Needs no Qt; tests/test_plugin.py runs it first.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "gui-plugin", "MaxxFanBridge")
STUBS = os.path.join(ROOT, "tests", "plugin_stubs")

# Members every Qt Quick object has, which plugin objects may set besides gui-v2's own.
QT_MEMBERS = {"id", "objectName", "x", "y", "z", "width", "height", "enabled", "anchors", "opacity",
              "scale", "implicitWidth", "implicitHeight", "parent", "children", "data"}


def api_types():
    with open(os.path.join(STUBS, "guiplugins-api.json")) as f:
        api = json.load(f)
    return {t["name"]: t for t in api["types"]}


def api_members(types, name):
    """Every member of a Victron.GuiPlugins type, with those of its Plugin* bases."""
    members = set()
    while name in types:
        t = types[name]
        for kind in ("properties", "methods", "signals"):
            members |= {m["name"] for m in t.get(kind, [])}
        for enum in t.get("enums", []):
            members |= {v["name"] for v in enum["values"]}
        name = t.get("base")
    return members


def check_api_use(plugin_dir=PLUGIN):
    """The plugin uses only types and members that gui-v2 v1.4.6 lists in guiplugins-api.json, and
    follows the plugin rules that a desktop can check (gui-v2's .github/gui-plugins.md)."""
    types = api_types()
    problems = []
    for qml in sorted(f for f in os.listdir(plugin_dir) if f.endswith(".qml")):
        with open(os.path.join(plugin_dir, qml)) as f:
            text = f.read()
        code = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        code = re.sub(r"//[^\n]*", "", code)
        imports = set(re.findall(r"^import ([\w.]+)", code, re.M))
        if imports - {"QtQuick", "QtQuick.Layouts", "Victron.GuiPlugins"}:
            problems.append("%s: imports %s" % (qml, imports))
        root_type = re.search(r"^([A-Z]\w*)\s*\{", code, re.M).group(1)
        expected = "PluginCard" if qml.endswith("_Card.qml") else "PluginPage"
        if root_type != expected:
            problems.append("%s: base type %s, not %s" % (qml, root_type, expected))

        # Objects and the properties set on them, by walking the braces.
        ids, stack = {}, []
        for line in code.splitlines():
            for m in re.finditer(r"(?:component\s+\w+\s*:\s*|property\s+\w+\s+\w+\s*:\s*)?"
                                 r"\b([A-Z]\w*)\s*\{|\{|\}|(?:^|(?<=[{;]))\s*([a-z]\w*(?:\.\w+)?)\s*:(?!:)", line):
                if m.group(0) == "}":
                    stack.pop()
                elif m.group(0) == "{":
                    stack.append("{")  # a JavaScript block or object: no properties of a type
                elif m.group(1):
                    stack.append(m.group(1))
                    if m.group(1).startswith("Plugin") and m.group(1) not in types:
                        problems.append("%s: no type %s in gui-v2" % (qml, m.group(1)))
                elif stack and m.group(2):
                    owner, member = stack[-1], m.group(2)
                    if member == "id":
                        ids[re.search(r"id\s*:\s*(\w+)", line[m.start():]).group(1)] = owner
                        continue
                    if not owner.startswith("Plugin") or re.match(r"(readonly |required )?property ", line.strip()):
                        continue
                    head, _, tail = member.partition(".")
                    if head.startswith("on") and head[2:3].isupper():
                        head = head[2].lower() + head[3:]  # a signal handler
                    if head not in api_members(types, owner) | QT_MEMBERS:
                        problems.append("%s: %s has no %s" % (qml, owner, head))
                    if tail and head == "dataItem" and tail not in api_members(types, "PluginDataItem"):
                        problems.append("%s: PluginDataItem has no %s" % (qml, tail))
        # Members read or called on Plugin objects by id, and on the singletons and enums. Names
        # the file declares itself (property, function, signal) are its own, not gui-v2's.
        own = set(re.findall(r"(?:property\s+[\w<>]+|function|signal)\s+(\w+)", code))
        for receiver, member in re.findall(r"\b(\w+)\.(\w+)", code):
            owner = ids.get(receiver, receiver if receiver in types else None)
            if owner and owner.startswith("Plugin") and member not in api_members(types, owner) | QT_MEMBERS | own:
                problems.append("%s: %s.%s is not in gui-v2" % (qml, receiver, member))
        if qml.endswith("_Card.qml"):
            for block in re.findall(r"PluginList\w+\s*\{(.*?)\n\t\}", code, re.S):
                if "flat: true" not in block:
                    problems.append("%s: a list item in a card must be flat" % qml)
    assert not problems, "\n".join(problems)
