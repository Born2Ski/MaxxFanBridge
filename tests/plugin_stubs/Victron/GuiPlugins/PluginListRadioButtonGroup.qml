import QtQuick
ListRow {
	id: root
	readonly property PluginDataItem dataItem: PluginDataItem {}
	property var optionModel: []
	readonly property int currentIndex: optionModel.findIndex(o => dataItem.valid && o.value === dataItem.value)
	property string defaultSecondaryText: PluginWords.unknown
	secondaryText: currentIndex >= 0 ? optionModel[currentIndex].display : defaultSecondaryText
	function pick(i) { if (interactive) dataItem.setValue(optionModel[i].value) }
}
