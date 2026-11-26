import QtQuick
// Stand-in: the devices of the fake bus with these service types and valid required paths, by name.
ListModel {
	id: model
	property var serviceTypes: []
	property var requiredPaths: []
	function serviceUidAt(i) { return i >= 0 && i < count ? get(i).serviceUid : "" }
	function nameAt(i) { return i >= 0 && i < count ? get(i).name : "" }
	function refresh() {
		clear()
		for (const device of fakeBus.devices(serviceTypes, requiredPaths)) {
			append(device)
		}
	}
	onServiceTypesChanged: refresh()
	onRequiredPathsChanged: refresh()
	Component.onCompleted: refresh()
	readonly property Connections watch: Connections {
		target: fakeBus
		function onDevicesChanged() { model.refresh() }
	}
}
