// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Pure view: parent validates and performs the emitted compositor requests.
// UNTESTED-LIVE.
pragma ComponentBehavior: Bound
import QtQuick
import "../runtime" as Runtime
import "../runtime/workspace_state.js" as Workspaces

FocusScope {
    id: root
    property int current: 1
    property var occupied: []
    property string style: "dots" // dots, bubbles, pill-group
    signal workspaceRequested(int workspace)
    signal specialRequested()
    implicitWidth: row.implicitWidth + (style === "pill-group" ? 12 : 0)
    implicitHeight: Math.max(36, row.implicitHeight + 8)
    Accessible.role: Accessible.Grouping
    Accessible.name: "Workspaces"
    Keys.onLeftPressed: function(event) { let next = Workspaces.step(root.current, -1); if (next !== null) root.workspaceRequested(next); event.accepted = true }
    Keys.onRightPressed: function(event) { let next = Workspaces.step(root.current, 1); if (next !== null) root.workspaceRequested(next); event.accepted = true }

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: root.style === "pill-group" ? Runtime.Theme.surface : "transparent"
        border.width: root.style === "pill-group" ? 1 : 0
        border.color: Runtime.Theme.outline
    }
    Row {
        id: row
        anchors.centerIn: parent
        spacing: Runtime.Theme.spacingSmall
        Repeater {
            model: 10
            Rectangle {
                id: dot
                required property int index
                readonly property int workspace: index + 1
                readonly property bool selected: workspace === root.current
                width: root.style === "bubbles" && selected ? 30 : 24
                height: width
                radius: height / 2
                color: selected ? Runtime.Theme.accent : (root.occupied.indexOf(workspace) >= 0 ? Runtime.Theme.outline : Runtime.Theme.surface)
                border.width: 1
                border.color: selected ? Runtime.Theme.accent : Runtime.Theme.outline
                Accessible.role: Accessible.Button
                Accessible.name: "Workspace " + workspace
                Text {
                    anchors.centerIn: parent
                    text: dot.workspace
                    color: dot.selected ? Runtime.Theme.accentForeground : Runtime.Theme.text
                    font.family: Runtime.Theme.fontUi
                    font.pixelSize: 10
                }
                MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton | Qt.MiddleButton
                    onClicked: function(mouse) {
                        root.forceActiveFocus()
                        if (mouse.button === Qt.MiddleButton) root.specialRequested()
                        else root.workspaceRequested(dot.workspace)
                    }
                    onWheel: function(wheel) {
                        let delta = wheel.angleDelta.y || wheel.angleDelta.x
                        if (delta !== 0) {
                            let next = Workspaces.step(root.current, delta > 0 ? -1 : 1)
                            if (next !== null) root.workspaceRequested(next)
                            wheel.accepted = true
                        }
                    }
                }
            }
        }
    }
}
