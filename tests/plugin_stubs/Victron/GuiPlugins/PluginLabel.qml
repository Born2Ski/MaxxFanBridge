import QtQuick
Item {
	id: root
	property string text
	property int fontSize: PluginPalette.font_size_medium
	property color color: PluginPalette.color_font_primary
	property int horizontalAlignment: Text.AlignLeft
	property int verticalAlignment: Text.AlignTop
	property int wrapMode: Text.NoWrap
	property int elide: Text.ElideNone
	implicitWidth: inner.implicitWidth
	implicitHeight: inner.implicitHeight
	Text {
		id: inner
		anchors.fill: parent
		text: root.text
		color: root.color
		font.pixelSize: root.fontSize
		horizontalAlignment: root.horizontalAlignment
		verticalAlignment: root.verticalAlignment
		wrapMode: root.wrapMode
		elide: root.elide
	}
}
