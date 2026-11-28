// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Read and explicitly request hyprsunset state; never launches the service.
// UNTESTED-LIVE.
import QtQuick
import Quickshell.Io

QtObject {
    id: root
    property bool active: false
    property string helper: ""
    property bool available: false
    property bool enabled: false
    property int temperature: 6500
    property string error: ""
    property bool busy: false
    property bool refreshPending: false
    signal completed(bool success)
    function request(action, value) {
        if (!active || !helper || busy || ["read", "set", "disable"].indexOf(action) < 0) return false
        if (action === "set" && (!Number.isInteger(value) || value < 1000 || value > 20000)) return false
        let args = ["python3", helper, action]
        if (action === "set") args.push(String(value))
        process.command = args
        busy = true
        requestTimeout.restart()
        process.running = true
        return true
    }
    function resumeRefresh() {
        if (!active || !refreshPending) return
        refreshPending = false
        Qt.callLater(function() { if (root.active && !root.busy) root.request("read") })
    }
    onActiveChanged: {
        if (active) {
            if (busy) refreshPending = true
            else request("read")
        } else { available = false; refreshPending = false }
    }
    // A set request can make three five-second compositor calls.
    property Timer requestTimeout: Timer {
        interval: 20000
        onTriggered: {
            if (!root.busy) return
            root.busy = false; root.available = false
            root.error = "Night-light helper timed out; requested changes may still have taken effect"
            process.running = false
            root.completed(false)
            root.resumeRefresh()
        }
    }
    property var processObject: Process {
        id: process
        stdout: StdioCollector { id: output }
        stderr: StdioCollector { id: errors }
        onRunningChanged: if (!running && root.busy) {
            root.requestTimeout.stop(); root.busy = false; root.available = false
            root.error = "Night-light helper unavailable"; root.completed(false); root.resumeRefresh()
        }
        onExited: function(exitCode, exitStatus) {
            if (!root.busy) return
            root.requestTimeout.stop(); root.busy = false
            if (exitCode !== 0 || exitStatus !== 0) {
                root.available = false; root.error = errors.text.slice(0, 500) || "Night-light helper failed"
                root.completed(false); root.resumeRefresh(); return
            }
            try {
                if (output.text.length > 4096) throw new Error("response too large")
                let state = JSON.parse(output.text)
                if (typeof state.enabled !== "boolean" || !Number.isInteger(state.temperature) || state.temperature < 1000 || state.temperature > 20000) throw new Error("invalid state")
                root.enabled = state.enabled; root.temperature = state.temperature; root.available = root.active; root.error = ""; root.completed(true)
            } catch (e) { root.available = false; root.error = "Invalid night-light response"; root.completed(false) }
            root.resumeRefresh()
        }
    }
}
