/*
** MaxxFanBridge: both fans on one page, opened by the Aangepast ("Custom") icon on the card.
** The same five controls per fan as MaxxFanBridge_Fan.qml. Plugin list items must be declared
** directly in the list, so the controls are written out once per fan.
*/

import QtQuick
import Victron.GuiPlugins

PluginPage {
	id: root

	// Set by the card: the fans' serviceUids and names, sorted by name.
	property string uid1
	property string name1
	property string uid2
	property string name2

	// A control's name, as renamed in the switch pane if it was. base: the fan's serviceUid.
	component OutputName: QtObject {
		property string base
		property string key
		readonly property string text: custom.valid && custom.value ? custom.value : name.valid ? name.value : key
		readonly property PluginDataItem name: PluginDataItem { uid: base + "/SwitchableOutput/" + key + "/Name" }
		readonly property PluginDataItem custom: PluginDataItem {
			uid: base + "/SwitchableOutput/" + key + "/Settings/CustomName"
		}
	}

	// A menu's entries as options: [{ display: "Inblazen", value: 0 }, ...].
	component Options: QtObject {
		property string base
		property string key
		readonly property var model: (labels.valid && labels.value ? labels.value : [])
			.map((label, index) => ({ display: label, value: index }))
		readonly property PluginDataItem labels: PluginDataItem {
			uid: base + "/SwitchableOutput/" + key + "/Settings/Labels"
		}
	}

	component Connected: QtObject {
		property string base
		readonly property bool value: item.valid && item.value === 1
		readonly property PluginDataItem item: PluginDataItem { uid: base + "/Connected" }
	}

	PluginItemListView {
		PluginSettingsListHeader {
			text: root.name1
			preferredVisible: root.uid1.length > 0
		}

		PluginListSwitch {
			text: names1.fan.text
			preferredVisible: root.uid1.length > 0
			dataItem.uid: root.uid1 + "/SwitchableOutput/fan/State"
			interactive: connected1.value
			writeAccessLevel: PluginAccessLevel.User
		}

		PluginListSlider {
			text: names1.speed.text
			preferredVisible: root.uid1.length > 0
			dataItem.uid: root.uid1 + "/SwitchableOutput/speed/Dimming"
			from: 10
			to: 100
			stepSize: 10
			interactive: connected1.value
			writeAccessLevel: PluginAccessLevel.User
		}

		PluginListRadioButtonGroup {
			text: names1.direction.text
			preferredVisible: root.uid1.length > 0
			dataItem.uid: root.uid1 + "/SwitchableOutput/direction/Dimming"
			optionModel: names1.directionOptions.model
			interactive: connected1.value
			writeAccessLevel: PluginAccessLevel.User
		}

		PluginListSwitch {
			text: names1.lid.text
			preferredVisible: root.uid1.length > 0
			dataItem.uid: root.uid1 + "/SwitchableOutput/lid/State"
			interactive: connected1.value
			writeAccessLevel: PluginAccessLevel.User
		}

		PluginListRadioButtonGroup {
			text: names1.mode.text
			preferredVisible: root.uid1.length > 0
			dataItem.uid: root.uid1 + "/SwitchableOutput/mode/Dimming"
			optionModel: names1.modeOptions.model
			interactive: connected1.value
			writeAccessLevel: PluginAccessLevel.User
		}

		PluginSettingsListHeader {
			text: root.name2
			preferredVisible: root.uid2.length > 0
		}

		PluginListSwitch {
			text: names2.fan.text
			preferredVisible: root.uid2.length > 0
			dataItem.uid: root.uid2 + "/SwitchableOutput/fan/State"
			interactive: connected2.value
			writeAccessLevel: PluginAccessLevel.User
		}

		PluginListSlider {
			text: names2.speed.text
			preferredVisible: root.uid2.length > 0
			dataItem.uid: root.uid2 + "/SwitchableOutput/speed/Dimming"
			from: 10
			to: 100
			stepSize: 10
			interactive: connected2.value
			writeAccessLevel: PluginAccessLevel.User
		}

		PluginListRadioButtonGroup {
			text: names2.direction.text
			preferredVisible: root.uid2.length > 0
			dataItem.uid: root.uid2 + "/SwitchableOutput/direction/Dimming"
			optionModel: names2.directionOptions.model
			interactive: connected2.value
			writeAccessLevel: PluginAccessLevel.User
		}

		PluginListSwitch {
			text: names2.lid.text
			preferredVisible: root.uid2.length > 0
			dataItem.uid: root.uid2 + "/SwitchableOutput/lid/State"
			interactive: connected2.value
			writeAccessLevel: PluginAccessLevel.User
		}

		PluginListRadioButtonGroup {
			text: names2.mode.text
			preferredVisible: root.uid2.length > 0
			dataItem.uid: root.uid2 + "/SwitchableOutput/mode/Dimming"
			optionModel: names2.modeOptions.model
			interactive: connected2.value
			writeAccessLevel: PluginAccessLevel.User
		}
	}

	// The names and menu entries of one fan's controls.
	component FanTexts: QtObject {
		property string base
		readonly property OutputName fan: OutputName { base: base_; key: "fan" }
		readonly property OutputName speed: OutputName { base: base_; key: "speed" }
		readonly property OutputName direction: OutputName { base: base_; key: "direction" }
		readonly property OutputName lid: OutputName { base: base_; key: "lid" }
		readonly property OutputName mode: OutputName { base: base_; key: "mode" }
		readonly property Options directionOptions: Options { base: base_; key: "direction" }
		readonly property Options modeOptions: Options { base: base_; key: "mode" }
		readonly property string base_: base
	}

	FanTexts { id: names1; base: root.uid1 }
	FanTexts { id: names2; base: root.uid2 }
	Connected { id: connected1; base: root.uid1 }
	Connected { id: connected2; base: root.uid2 }
}
