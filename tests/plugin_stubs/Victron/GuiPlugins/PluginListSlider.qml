import QtQuick
ListRow {
	id: root
	readonly property PluginDataItem dataItem: PluginDataItem {}
	property real from: 0
	property real to: 1
	property real stepSize: (to - from) / 10
	readonly property real value: dataItem.valid ? dataItem.value : from
	secondaryText: dataItem.valid ? value : "--"
	function move(v) { if (interactive) dataItem.setValue(v) }
}
