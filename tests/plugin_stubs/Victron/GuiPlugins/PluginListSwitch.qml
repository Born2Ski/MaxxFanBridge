import QtQuick
ListRow {
	id: root
	readonly property PluginDataItem dataItem: PluginDataItem {}
	property var valueTrue: 1
	property var valueFalse: 0
	readonly property bool checked: dataItem.valid && dataItem.value === valueTrue
	signal clicked
	secondaryText: checked ? PluginWords.on : PluginWords.off
	function click() { if (interactive) { clicked(); dataItem.setValue(checked ? valueFalse : valueTrue) } }
}
