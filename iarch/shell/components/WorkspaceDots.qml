// Copyright (C) 2026 Safari — GPL-3.0-or-later
pragma ComponentBehavior: Bound
import QtQuick
import "../runtime" as Runtime

Item {
    id: root
    property int count: 1
    property int current: 0 // zero-based
    property string shape: "dots" // dots, bubbles, pill or pill-group
    signal selected(int index)
    implicitWidth: dots.implicitWidth + (shape === "pill" || shape === "pill-group" ? 12 : 0)
    implicitHeight: Math.max(24, dots.implicitHeight + 8)
    Accessible.name: "Workspaces"
    Rectangle {
        anchors.fill: parent
        visible: root.shape === "pill" || root.shape === "pill-group"
        radius: height / 2
        color: Runtime.Theme.surface
        border.color: Runtime.Theme.outline
    }
    Row {
        id: dots
        anchors.centerIn: parent
        spacing: Runtime.Theme.spacingSmall
        Repeater {
            model: Math.max(0, Math.min(root.count, 100))
            Rectangle {
                id: dot
                required property int index
                readonly property bool selected: index === root.current
                width: root.shape === "bubbles" && selected ? 20 : 14
                height: width
                radius: height / 2
                color: selected ? Runtime.Theme.accent : Runtime.Theme.outline
                Accessible.role: Accessible.Button
                Accessible.name: "Workspace " + (index + 1)
                Text { anchors.centerIn: parent; text: dot.index + 1; color: dot.selected ? Runtime.Theme.accentForeground : Runtime.Theme.text; font.family: Runtime.Theme.fontUi; font.pixelSize: 8 }
                MouseArea { anchors.fill: parent; onClicked: root.selected(dot.index) }
            }
        }
    }
}
