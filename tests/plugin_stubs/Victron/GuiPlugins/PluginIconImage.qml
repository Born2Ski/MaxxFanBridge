import QtQuick
import QtQuick.Controls.impl as CP
// Same drawing as gui-v2's PluginIconImage.
Item {
	id: root
	enum Tint { Text, SecondaryText, Warning, Critical, Success, Brand, Disabled }
	property url source
	property int tint: PluginIconImage.Text
	implicitWidth: 32
	implicitHeight: 32
	CP.ColorImage {
		anchors.fill: parent
		source: root.source
		sourceSize.width: width
		sourceSize.height: height
		fillMode: Image.PreserveAspectFit
		color: !root.enabled || root.tint === PluginIconImage.Disabled ? PluginPalette.color_font_disabled
			: root.tint === PluginIconImage.Brand ? PluginPalette.color_brand
			: root.tint === PluginIconImage.SecondaryText ? PluginPalette.color_font_secondary
			: PluginPalette.color_font_primary
	}
}
