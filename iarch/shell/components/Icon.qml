// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import QtQuick.Effects
import "../runtime" as Runtime

Item {
    id: root
    // A closed name avoids interpreting user strings as filesystem paths or URLs.
    property string name: ""
    property string glyph: ""
    property color tint: Runtime.Theme.text
    readonly property var names: ["wifi", "battery", "bluetooth", "volume-2", "sun", "bell", "clock", "calendar", "search", "x", "settings"]
    readonly property bool known: names.indexOf(name) >= 0
    implicitWidth: 24; implicitHeight: 24
    Accessible.name: name || glyph
    Image {
        id: iconImage
        anchors.fill: parent
        source: root.known ? "../assets/icons/shell/" + root.name + ".svg" : ""
        sourceSize.width: Math.ceil(root.width)
        sourceSize.height: Math.ceil(root.height)
        fillMode: Image.PreserveAspectFit
        visible: false
    }
    MultiEffect {
        anchors.fill: parent
        source: iconImage
        colorization: 1
        colorizationColor: root.tint
        visible: root.known && iconImage.status === Image.Ready
    }
    Text {
        anchors.fill: parent
        visible: !root.known || iconImage.status === Image.Error
        text: root.glyph
        color: root.tint
        font.family: Runtime.Theme.fontUi
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
}
