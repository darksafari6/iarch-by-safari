// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Event-driven snapshot with fixed-argument layout requests. UNTESTED-LIVE.
import QtQuick
import Quickshell.Io
import Quickshell.Hyprland
import "keyboard.js" as KeyboardParser

QtObject {
    id: root
    property bool active: false
    property bool available: false
    property string error: ""
    property string name: ""
    property string layout: ""
    property bool capsLock: false
    property bool numLock: false
    property bool pendingRefresh: false
    property bool reading: false
    property bool changing: false
    signal switchFinished(bool success)
    function refresh() {
        if (!active) return
        if (reader.running || reading) { pendingRefresh = true; return }
        reading = true
        readTimeout.restart()
        reader.running = true
    }
    function cycle(direction) {
        if (!active || !available || changing || (direction !== "next" && direction !== "prev")) return false
        changing = true
        writer.command = ["hyprctl", "switchxkblayout", "current", direction]
        writeTimeout.restart()
        writer.running = true
        return true
    }
    onActiveChanged: {
        if (active) refresh()
        else { readTimeout.stop(); reader.running = false; pendingRefresh = false; reading = false; available = false }
    }
    property Connections events: Connections {
        target: Hyprland
        enabled: root.active
        function onRawEvent(event) {
            if (event.name === "activelayout" || event.name === "configreloaded") root.refresh()
        }
    }
    property Timer readTimeout: Timer {
        interval: 5000
        onTriggered: { root.reading = false; root.pendingRefresh = false; reader.running = false; root.available = false; root.error = "Keyboard query timed out" }
    }
    property Timer writeTimeout: Timer {
        interval: 5000
        onTriggered: { root.changing = false; writer.running = false; root.error = "Layout switch timed out"; root.switchFinished(false) }
    }
    property var readProcess: Process {
        id: reader
        command: ["hyprctl", "-j", "devices"]
        stdout: StdioCollector { id: readOutput }
        onRunningChanged: if (!running && root.reading) { readTimeout.stop(); root.reading = false; root.available = false; root.error = "Keyboard query unavailable" }
        onExited: function(exitCode, exitStatus) {
            if (!root.reading) return
            readTimeout.stop()
            root.reading = false
            let data = exitCode === 0 && exitStatus === 0 ? KeyboardParser.parse(readOutput.text) : null
            if (data && root.active) {
                root.name = data.name; root.layout = data.layout; root.capsLock = data.capsLock; root.numLock = data.numLock
                root.available = true; root.error = ""
            } else if (root.active) { root.available = false; root.error = "Keyboard query failed or returned invalid data" }
            if (root.pendingRefresh) { root.pendingRefresh = false; root.refresh() }
        }
    }
    property var writeProcess: Process {
        id: writer
        stdout: StdioCollector { id: writeOutput }
        onRunningChanged: if (!running && root.changing) { writeTimeout.stop(); root.changing = false; root.error = "Layout switch unavailable"; root.switchFinished(false) }
        onExited: function(exitCode, exitStatus) {
            if (!root.changing) return
            writeTimeout.stop()
            root.changing = false
            let success = exitCode === 0 && exitStatus === 0 && writeOutput.text.trim() === "ok"
            if (!success) root.error = "Layout switch failed"
            root.switchFinished(success)
            root.refresh()
        }
    }
}
