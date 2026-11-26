import QtQuick
// Stand-in: one value of the fake bus (tests/test_plugin.py), by uid.
QtObject {
	id: item
	property string uid
	property var value: undefined
	property bool valid: false
	function setValue(v) { fakeBus.write(uid, v) }
	function refresh() { valid = uid.length > 0 && fakeBus.has(uid); value = valid ? fakeBus.value(uid) : undefined }
	onUidChanged: refresh()
	Component.onCompleted: refresh()
	readonly property Connections watch: Connections {
		target: fakeBus
		function onChanged(changedUid) { if (changedUid === item.uid) item.refresh() }
	}
}
