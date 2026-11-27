import QtQuick

Text {
    property string sortScope: ""
    property string sortKey: ""
    property string sortKind: "text"
    signal sortRequested(string scope, string key, string kind)

    color: "#a6b0b4"
    font.pixelSize: 11
    verticalAlignment: Text.AlignVCenter
    elide: Text.ElideRight

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: parent.sortRequested(parent.sortScope, parent.sortKey, parent.sortKind)
    }
}
