/*
** MaxxFanBridge: one card in the gui-v2 switch pane for the MaxxFans.
**
** A row of preset icons (the one that is on is lit; "Aangepast" is lit when none is), and a row
** per fan that opens its page. Tapping Aangepast opens both fans on one page.
**
** The card only reads and writes the D-Bus paths of dbus-maxxfan-bridge, exactly as the switch-pane
** cards do, so the driver handles a tap here like a touch there. Every text comes from the driver
** (names, menu entries), so it follows [gui] language in config.ini. Needs gui-v2 1.4.6 or later.
*/

import QtQuick
import Victron.GuiPlugins

PluginCard {
	id: root

	// The driver's services, found by paths that only they have.
	readonly property string presetsUid: presetServices.count > 0 ? presetServices.serviceUidAt(0) : ""
	readonly property var presetKeys: presetKeysItem.valid && presetKeysItem.value ? presetKeysItem.value : []
	readonly property string customText: customTextItem.valid ? customTextItem.value : ""
	readonly property bool anyFanConnected: {
		for (let i = 0; i < fans.count; ++i) {
			const fan = fans.objectAt(i)
			if (fan && fan.connected) {
				return true
			}
		}
		return false
	}
	// The key of the preset that is on, or "" when none is.
	readonly property string activeKey: {
		for (let i = 0; i < presets.count; ++i) {
			const preset = presets.objectAt(i)
			if (preset && preset.on) {
				return preset.key
			}
		}
		return ""
	}
	readonly property var knownIcons: ["cooking", "sleep", "drive", "standard"]

	function presetLabel(key) {
		for (let i = 0; i < presets.count; ++i) {
			const preset = presets.objectAt(i)
			if (preset && preset.key === key) {
				return preset.label
			}
		}
		return key
	}

	function iconFor(key) {
		return Qt.resolvedUrl("icon_" + (knownIcons.indexOf(key) >= 0 ? key : "preset") + ".svg")
	}

	function fanAt(index) {
		return index < fans.count ? fans.objectAt(index) : null
	}

	title: titleItem.valid ? titleItem.value : ""
	status: presetsUid.length === 0 ? "" : activeKey.length > 0 ? presetLabel(activeKey) : customText
	iconSource: Qt.resolvedUrl("icon_fan.svg")

	// A preset icon: lit when it is the one that is on.
	component Tile: Item {
		id: tile

		property string key
		property url icon
		property string label
		property bool lit
		property real labelScale: 1  // the same for every tile: the largest at which all names fit
		readonly property real fit: Math.min(1, (width - 6) / Math.max(1, nameLabel.implicitWidth))
		signal tapped

		objectName: "tile_" + key
		height: 84

		Rectangle {
			anchors.fill: parent
			radius: 8
			color: tile.lit ? Qt.alpha(PluginPalette.color_brand, 0.25) : "transparent"
			border.width: tile.lit ? 2 : 1
			border.color: tile.lit ? PluginPalette.color_brand : Qt.alpha(PluginPalette.color_font_secondary, 0.4)
		}

		PluginIconImage {
			anchors.horizontalCenter: parent.horizontalCenter
			y: 10
			width: 36
			height: 36
			enabled: tile.enabled
			source: tile.icon
			tint: tile.lit ? PluginIconImage.Brand : PluginIconImage.Text
		}

		// The name on one line, made smaller when a name is wider than its tile ("Standaard").
		PluginLabel {
			id: nameLabel

			anchors.horizontalCenter: parent.horizontalCenter
			y: 54
			text: tile.label
			fontSize: PluginPalette.font_size_small
			color: !tile.enabled ? PluginPalette.color_font_disabled
				: tile.lit ? PluginPalette.color_font_primary : PluginPalette.color_font_secondary
			scale: tile.labelScale
		}

		MouseArea {
			anchors.fill: parent
			enabled: tile.enabled
			onClicked: tile.tapped()
		}
	}

	Row {
		id: tiles

		readonly property int tileCount: root.presetKeys.length + 1
		readonly property real tileWidth: (width - spacing * (tileCount - 1)) / tileCount
		readonly property real labelScale: {
			let smallest = 1
			for (const child of children) {
				if (child.fit !== undefined) {
					smallest = Math.min(smallest, child.fit)
				}
			}
			return smallest
		}

		x: root.contentMargin
		width: root.width - 2 * root.contentMargin
		height: 84
		spacing: 6
		visible: root.presetsUid.length > 0

		Repeater {
			model: root.presetKeys

			delegate: Tile {
				required property var modelData

				key: modelData
				width: tiles.tileWidth
				labelScale: tiles.labelScale
				icon: root.iconFor(modelData)
				label: root.presetLabel(modelData)
				lit: root.activeKey === modelData
				// The driver refuses a preset while none of its fans is connected.
				enabled: root.anyFanConnected
				onTapped: root.choose(modelData)
			}
		}

		Tile {
			key: "custom"
			width: tiles.tileWidth
			labelScale: tiles.labelScale
			icon: Qt.resolvedUrl("icon_custom.svg")
			label: root.customText
			lit: root.activeKey.length === 0
			onTapped: allFans.click()
		}
	}

	Item {
		width: 1
		height: 8
	}

	// One row per fan, sorted by name (Bed, Keuken), opening its page. The card shows two fans.
	PluginListNavigation {
		objectName: "fanRow0"
		flat: true
		preferredVisible: fans.count > 0
		text: root.fanAt(0)?.name ?? ""
		secondaryText: root.fanAt(0)?.summary ?? ""
		pageUrl: Qt.resolvedUrl("MaxxFanBridge_Fan.qml")
		pageProperties: ({ serviceUid: root.fanAt(0)?.serviceUid ?? "", title: root.fanAt(0)?.name ?? "" })
	}

	PluginListNavigation {
		objectName: "fanRow1"
		flat: true
		preferredVisible: fans.count > 1
		text: root.fanAt(1)?.name ?? ""
		secondaryText: root.fanAt(1)?.summary ?? ""
		pageUrl: Qt.resolvedUrl("MaxxFanBridge_Fan.qml")
		pageProperties: ({ serviceUid: root.fanAt(1)?.serviceUid ?? "", title: root.fanAt(1)?.name ?? "" })
	}

	// Not shown: the Aangepast icon opens both fans through it.
	PluginListNavigation {
		id: allFans

		objectName: "allFans"
		flat: true
		preferredVisible: false
		text: root.customText
		pageUrl: Qt.resolvedUrl("MaxxFanBridge_AllFans.qml")
		pageProperties: ({
			title: root.title,
			uid1: root.fanAt(0)?.serviceUid ?? "", name1: root.fanAt(0)?.name ?? "",
			uid2: root.fanAt(1)?.serviceUid ?? "", name2: root.fanAt(1)?.name ?? ""
		})
	}

	function choose(key) {
		if (root.presetsUid.length > 0) {
			chooser.uid = root.presetsUid + "/SwitchableOutput/" + key + "/State"
			chooser.setValue(1)
		}
	}

	PluginDataItem {
		id: chooser
	}

	PluginDeviceModel {
		id: presetServices

		serviceTypes: ["switch"]
		requiredPaths: ["MaxxFan/PresetKeys"]
	}

	PluginDataItem {
		id: presetKeysItem

		uid: root.presetsUid.length > 0 ? root.presetsUid + "/MaxxFan/PresetKeys" : ""
	}

	PluginDataItem {
		id: customTextItem

		uid: root.presetsUid.length > 0 ? root.presetsUid + "/MaxxFan/CustomText" : ""
	}

	PluginDataItem {
		id: titleItem

		uid: root.presetsUid.length > 0 ? root.presetsUid + "/CustomName" : ""
	}

	// Each preset: whether it is on, and its name (as renamed in the switch pane, if it was).
	Instantiator {
		id: presets

		model: root.presetKeys
		delegate: QtObject {
			required property var modelData

			readonly property string key: modelData
			readonly property bool on: state.valid && state.value === 1
			readonly property string label: customName.valid && customName.value ? customName.value
				: name.valid ? name.value : key

			readonly property PluginDataItem state: PluginDataItem {
				uid: root.presetsUid + "/SwitchableOutput/" + modelData + "/State"
			}
			readonly property PluginDataItem name: PluginDataItem {
				uid: root.presetsUid + "/SwitchableOutput/" + modelData + "/Name"
			}
			readonly property PluginDataItem customName: PluginDataItem {
				uid: root.presetsUid + "/SwitchableOutput/" + modelData + "/Settings/CustomName"
			}
		}
	}

	// Each fan: its name and a short summary for its row, such as "Afzuigen 80 %".
	Instantiator {
		id: fans

		model: PluginDeviceModel {
			serviceTypes: ["switch"]
			requiredPaths: ["MaxxFan/Fan"]
		}
		delegate: QtObject {
			required property string serviceUid
			required property string name

			readonly property bool connected: connectedItem.valid && connectedItem.value === 1
			readonly property string summary: {
				if (!connected) {
					return "—"
				}
				const labels = (items) => items.valid && items.value ? items.value : []
				if (mode.valid && mode.value === 1) {
					return labels(modeLabels)[1] ?? PluginWords.auto
				}
				if (!(on.valid && on.value === 1)) {
					return PluginWords.off
				}
				const direction = labels(directionLabels)[direction_.value] ?? ""
				return (direction + " " + (speed.valid ? speed.value + " %" : "")).trim()
			}

			readonly property PluginDataItem connectedItem: PluginDataItem { uid: serviceUid + "/Connected" }
			readonly property PluginDataItem on: PluginDataItem { uid: serviceUid + "/SwitchableOutput/fan/State" }
			readonly property PluginDataItem speed: PluginDataItem { uid: serviceUid + "/SwitchableOutput/speed/Dimming" }
			readonly property PluginDataItem direction_: PluginDataItem { uid: serviceUid + "/SwitchableOutput/direction/Dimming" }
			readonly property PluginDataItem directionLabels: PluginDataItem { uid: serviceUid + "/SwitchableOutput/direction/Settings/Labels" }
			readonly property PluginDataItem mode: PluginDataItem { uid: serviceUid + "/SwitchableOutput/mode/Dimming" }
			readonly property PluginDataItem modeLabels: PluginDataItem { uid: serviceUid + "/SwitchableOutput/mode/Settings/Labels" }
		}
	}
}
