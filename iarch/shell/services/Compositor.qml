// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Event-driven Hyprland state via Quickshell. UNTESTED-LIVE.
import QtQuick
import Quickshell.Hyprland

QtObject {
    id: root
    property bool active: false
    readonly property bool available: active && Hyprland.focusedMonitor !== null
    readonly property string error: active && !available ? "Compositor information unavailable" : ""
    readonly property var monitors: active ? Hyprland.monitors.values : []
    readonly property var workspaces: active ? Hyprland.workspaces.values : []
    readonly property var windows: active ? Hyprland.toplevels.values : []
    readonly property var focusedWorkspace: active ? Hyprland.focusedWorkspace : null
    readonly property var activeWindow: active ? Hyprland.activeToplevel : null
    signal compositorEvent(var event)
    property Connections events: Connections {
        target: Hyprland
        enabled: root.active
        function onRawEvent(event) { root.compositorEvent(event) }
    }
}
