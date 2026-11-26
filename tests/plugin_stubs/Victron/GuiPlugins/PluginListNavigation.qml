import QtQuick
// Stand-in: click() as gui-v2's (only checks interactive), and records the page it opens.
ListRow {
	id: root
	property url pageUrl
	property var pageProperties: ({})
	signal clicked
	function click() {
		if (!interactive) return
		clicked()
		if (pageUrl.toString().length > 0) fakeBus.pushPage(pageUrl.toString(), Object.assign({}, pageProperties), text)
	}
	MouseArea { anchors.fill: parent; onClicked: root.click() }
}
