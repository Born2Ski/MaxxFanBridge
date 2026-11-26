Stand-ins for gui-v2's `Victron.GuiPlugins` QML module, used by `tests/test_plugin.py` to run
the plugin card (`gui-plugin/MaxxFanBridge`) on a desktop. They follow the behaviour documented
in gui-v2's `.github/gui-plugins.md` (v1.4.6), with only the members the plugin uses, and their
data comes from the driver's own services. They are not gui-v2: the real look and the real
module are only seen on a Venus OS device with gui-v2 1.4.6 or later.

`guiplugins-api.json` is copied unchanged from gui-v2 v1.4.6 (`tools/guiplugins-api.json`):
the list of types and members in `Victron.GuiPlugins`. The test checks the plugin against it, so
it cannot pass by using a member that gui-v2 does not have. Copyright (c) 2023 Victron Energy,
under the licence in `GUI-V2-LICENSE.txt`.
