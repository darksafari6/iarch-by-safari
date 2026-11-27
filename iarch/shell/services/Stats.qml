// Copyright (C) 2026 Safari — GPL-3.0-or-later
// UNTESTED-LIVE: demand-driven local /proc and filesystem statistics.
import QtQuick
import Quickshell.Io
import "sample_validation.js" as Samples

QtObject {
    id: root
    property bool active: false
    property string helper: ""
    property bool available: false
    property bool inFlight: false
    property string error: ""
    property var sample: ({})
    property var previousCpu: null
    property real cpuPercent: -1
    property int interval: 3000
    function refresh() {
        if (active && helper && !reader.running) {
            reader.command = ["python3", helper]
            inFlight = true
            reader.running = true
        }
    }
    onActiveChanged: {
        if (active && !helper) { available = false; error = "Statistics helper is unavailable" }
        else if (active) refresh()
        else { inFlight = false; reader.running = false; previousCpu = null; cpuPercent = -1 }
    }
    property Timer timer: Timer {
        interval: Math.max(1000, root.interval)
        repeat: true
        running: root.active
        onTriggered: root.refresh()
    }
    property var process: Process {
        id: reader
        stdout: StdioCollector { id: output }
        onRunningChanged: {
            if (!running && root.inFlight) {
                root.inFlight = false
                root.available = false
                root.error = "Unable to start statistics reader"
            }
        }
        onExited: function(exitCode, exitStatus) {
            root.inFlight = false
            if (!root.active) return
            if (exitCode !== 0 || exitStatus !== 0) {
                root.available = false
                root.error = "Unable to read statistics"
                return
            }
            try {
                if (output.text.length > 1048576) throw new Error("sample too large")
                let value = JSON.parse(output.text)
                if (!Samples.stats(value)) throw new Error("invalid sample")
                if (Array.isArray(value.cpu) && value.cpu.length === 2 && root.previousCpu) {
                    let total = value.cpu[0] - root.previousCpu[0]
                    let idle = value.cpu[1] - root.previousCpu[1]
                    root.cpuPercent = total > 0 && idle >= 0 && idle <= total ? 100 * (total - idle) / total : -1
                }
                root.previousCpu = value.cpu
                root.sample = value
                root.available = value.cpu !== null || value.memory !== null || value.disk !== null || value.temperature !== null
                root.error = Object.keys(value.errors).join(", ")
            } catch (e) { root.available = false; root.error = "Invalid statistics sample" }
        }
    }
}
