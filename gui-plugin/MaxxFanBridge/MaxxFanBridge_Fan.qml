/*
** MaxxFanBridge: one fan's page, opened from its row on the card. The same five controls as its
** switch-pane card, with the names, menu entries and limits the driver gives.
*/

import QtQuick
import Victron.GuiPlugins

PluginPage {
	id: root

	property string serviceUid  // set by the card: com.victronenergy.switch.maxxfan_<id>

	readonly property bool connected: connectedItem.valid && connectedItem.value === 1

	function out(key, leaf) {
		return root.serviceUid + "/SwitchableOutput/" + key + "/" + leaf
	}

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

	PluginItemListView {
		PluginListSwitch {
			text: fanName.text
			dataItem.uid: root.out("fan", "State")
			interactive: root.connected
			writeAccessLevel: PluginAccessLevel.User
		}

		PluginListSlider {
			text: speedName.text
			dataItem.uid: root.out("speed", "Dimming")
			from: 10
			to: 100
			stepSize: 10
			interactive: root.connected
			writeAccessLevel: PluginAccessLevel.User
		}

		PluginListRadioButtonGroup {
			text: directionName.text
			dataItem.uid: root.out("direction", "Dimming")
			optionModel: directionOptions.model
			interactive: root.connected
			writeAccessLevel: PluginAccessLevel.User
		}

		PluginListSwitch {
			text: lidName.text
			dataItem.uid: root.out("lid", "State")
			interactive: root.connected
			writeAccessLevel: PluginAccessLevel.User
		}

		PluginListRadioButtonGroup {
			text: modeName.text
			dataItem.uid: root.out("mode", "Dimming")
			optionModel: modeOptions.model
			interactive: root.connected
			writeAccessLevel: PluginAccessLevel.User
		}
	}

	PluginDataItem { id: connectedItem; uid: root.serviceUid + "/Connected" }
	OutputName { id: fanName; base: root.serviceUid; key: "fan" }
	OutputName { id: speedName; base: root.serviceUid; key: "speed" }
	OutputName { id: directionName; base: root.serviceUid; key: "direction" }
	OutputName { id: lidName; base: root.serviceUid; key: "lid" }
	OutputName { id: modeName; base: root.serviceUid; key: "mode" }
	Options { id: directionOptions; base: root.serviceUid; key: "direction" }
	Options { id: modeOptions; base: root.serviceUid; key: "mode" }
}
