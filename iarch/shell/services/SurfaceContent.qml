// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Minimal, read-only shell-core status view. Full surface designs belong to
// subsequent milestones. Pure QtQuick so it can be loaded without Quickshell.
// UNTESTED-LIVE: compositor geometry and real service bindings.
pragma ComponentBehavior: Bound
import QtQuick
import "../runtime" as Runtime

Item {
    id: root
    property string surfaceName: ""
    property var services: ({})
    property bool vertical: false
    readonly property var clock: services.clock || null
    readonly property var battery: services.battery || null
    readonly property var network: services.network || null
    readonly property var audio: services.audio || null
    readonly property var media: services.media || null
    readonly property var stats: services.stats || null
    readonly property var todo: services.todo || null
    readonly property string clockLabel: clock && clock.available ? clock.timeText : "Clock unavailable"
    readonly property string batteryLabel: battery && battery.available ? "Battery " + Math.round(battery.percentage * 100) + "%" : "Battery unavailable"
    readonly property string networkLabel: network && network.available ? (network.ssid || "No Wi-Fi connection") : "Network unavailable"
    readonly property string audioLabel: audio && audio.available ? (audio.muted ? "Audio muted" : "Volume " + Math.round(audio.volume * 100) + "%") : "Audio unavailable"
    readonly property string mediaLabel: media && media.available ? (media.title || "Untitled track") : "No media player"
    readonly property string cpuLabel: stats && stats.available && stats.cpuPercent >= 0 ? "CPU " + Math.round(stats.cpuPercent) + "%" : "CPU unavailable"
    readonly property string todoLabel: todo && todo.available ? "Tasks " + todo.items.length : "Tasks unavailable"

    Text {
        anchors.centerIn: parent
        width: parent.width - 24
        visible: root.surfaceName === "bar"
        text: root.vertical ? root.clockLabel + "\n" + root.batteryLabel :
              "iArch by Safari   " + root.clockLabel + "   " + root.batteryLabel + "   " + root.networkLabel
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        color: Runtime.Theme.text
        font.family: Runtime.Theme.fontUi
    }
    Column {
        anchors.fill: parent
        anchors.margins: Runtime.Theme.spacingLarge
        spacing: Runtime.Theme.spacingMedium
        visible: root.surfaceName !== "bar"
        Text {
            width: parent.width
            text: root.surfaceName === "sidebar-right" ? "System status" :
                  root.surfaceName === "sidebar-left" ? "Today" : root.surfaceName
            color: Runtime.Theme.text
            font.family: Runtime.Theme.fontDisplay
            font.pixelSize: 20
            elide: Text.ElideRight
        }
        Repeater {
            model: root.surfaceName === "sidebar-right" ?
                   [root.batteryLabel, root.networkLabel, root.audioLabel, root.mediaLabel, root.cpuLabel] :
                   root.surfaceName === "sidebar-left" ?
                   [root.clock && root.clock.available ? root.clock.dateText : "Date unavailable", root.todoLabel] : []
            Text {
                required property string modelData
                width: parent.width
                text: modelData
                color: Runtime.Theme.text
                font.family: Runtime.Theme.fontUi
                elide: Text.ElideRight
            }
        }
    }
}
