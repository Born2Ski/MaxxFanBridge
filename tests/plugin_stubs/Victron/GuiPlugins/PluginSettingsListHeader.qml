import QtQuick
Item {
	property string text
	property bool preferredVisible: true
	visible: preferredVisible
	width: parent ? parent.width : 800
	height: visible ? 36 : 0
	Text { x: 16; anchors.bottom: parent.bottom; text: parent.text; color: PluginPalette.color_font_secondary; font.pixelSize: PluginPalette.font_size_small }
}
