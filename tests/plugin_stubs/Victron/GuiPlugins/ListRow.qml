import QtQuick
// Shared look of the stand-in list items: text on the left, secondary text on the right.
Item {
	id: row
	property string text
	property string caption
	property string secondaryText
	property bool flat
	property bool preferredVisible: true
	property int showAccessLevel: 0
	property int writeAccessLevel: 1
	property bool interactive: true
	readonly property bool effectiveVisible: preferredVisible
	visible: preferredVisible
	width: parent ? parent.width : 368
	height: visible ? 52 : 0
	Rectangle { anchors.fill: parent; visible: !row.flat; color: PluginPalette.color_background_secondary; radius: 6 }
	Text { x: 16; anchors.verticalCenter: parent.verticalCenter; text: row.text; font.pixelSize: PluginPalette.font_size_medium; color: row.interactive ? PluginPalette.color_font_primary : PluginPalette.color_font_disabled }
	Text { anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter; text: row.secondaryText; font.pixelSize: PluginPalette.font_size_medium; color: PluginPalette.color_font_secondary }
}
