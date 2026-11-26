import QtQuick
// Stand-in for gui-v2's PluginCard at the 800x480 ("five inch") control-card size.
Item {
	id: root
	default property alias content: column.data
	property url iconSource
	property string title
	property string status
	readonly property real contentMargin: 16
	width: 368
	height: 408
	Rectangle { anchors.fill: parent; radius: 8; color: PluginPalette.color_background_secondary }
	PluginIconImage { x: 16; y: 16; width: 24; height: 24; source: root.iconSource }
	Text { objectName: "cardTitle"; x: 48; y: 18; text: root.title; color: PluginPalette.color_font_secondary; font.pixelSize: PluginPalette.font_size_small }
	Text { objectName: "cardStatus"; id: status; x: 16; y: 46; text: root.status; color: PluginPalette.color_font_primary; font.pixelSize: PluginPalette.font_size_large }
	Column { id: column; y: status.y + status.height + 6; width: parent.width }
}
