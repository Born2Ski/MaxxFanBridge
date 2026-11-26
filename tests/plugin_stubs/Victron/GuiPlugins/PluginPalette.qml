pragma Singleton
import QtQuick
// Stand-in for gui-v2's PluginPalette, dark mode.
QtObject {
	readonly property color color_background_primary: "#000000"
	readonly property color color_background_secondary: "#1c1c1e"
	readonly property color color_background_page: "#000000"
	readonly property color color_font_primary: "#ffffff"
	readonly property color color_font_secondary: "#969591"
	readonly property color color_font_disabled: "#5a5a5a"
	readonly property color color_brand: "#387dc5"
	readonly property color color_info: "#387dc5"
	readonly property color color_success: "#72b84c"
	readonly property color color_warning: "#f0962e"
	readonly property color color_critical: "#f35c58"
	readonly property string font_family: ""
	readonly property string quantity_font_family: ""
	readonly property int font_size_small: 16
	readonly property int font_size_medium: 18
	readonly property int font_size_large: 28
	readonly property int orientation: Qt.LandscapeOrientation
}
