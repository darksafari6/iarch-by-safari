// Copyright (C) 2026 Safari — GPL-3.0-or-later
// brightnessctl 0.5.1 machine-readable adapter. UNTESTED-LIVE.
import QtQuick
import Quickshell.Io
import "brightness.js" as Parser

QtObject {
    id: root
    property bool active: false
    property bool available: false
    property string error: ""
    property int percent: 0
    property real maximum: 0
    property bool readPending: false
    property bool writePending: false
    property int interval: 5000
    function refresh() {
        if (!active || reader.running) return
        readPending = true
        reader.running = true
    }
    function setPercent(value) {
        if (!active || !available || writer.running || typeof value !== "number" ||
                !Number.isInteger(value) || value < 1 || value > 100) return false
        writePending = true
        writer.command = ["brightnessctl", "--class=backlight", "set", String(Math.max(1, Math.round(maximum * value / 100)))]
        writer.running = true
        return true
    }
    onActiveChanged: {
        if (active) refresh()
        else { readPending = false; writePending = false; reader.running = false; writer.running = false }
    }
    property Timer timer: Timer { interval: Math.max(1000, root.interval); repeat: true; running: root.active; onTriggered: root.refresh() }
    property var readProcess: Process {
        id: reader
        command: ["brightnessctl", "--class=backlight", "--machine-readable", "info"]
        stdout: StdioCollector { id: output }
        onRunningChanged: if (!running && root.readPending) { root.readPending = false; root.available = false; root.error = "Brightness tool unavailable" }
        onExited: function(exitCode, exitStatus) {
            root.readPending = false
            if (!root.active) return
            let value = exitCode === 0 && exitStatus === 0 ? Parser.parse(output.text) : null
            if (!value) { root.available = false; root.error = "Unable to read brightness"; return }
            root.percent = value.percent
            root.maximum = value.maximum
            root.available = true
            root.error = ""
        }
    }
    property var writeProcess: Process {
        id: writer
        onRunningChanged: if (!running && root.writePending) { root.writePending = false; root.error = "Brightness tool unavailable" }
        onExited: function(exitCode, exitStatus) {
            root.writePending = false
            if (!root.active) return
            if (exitCode !== 0 || exitStatus !== 0) { root.error = "Brightness change failed"; return }
            root.refresh()
        }
    }
}
