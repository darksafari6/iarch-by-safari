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
    signal completed(bool success)
    function request(action, value) {
        if (!active || !helper || busy || ["read", "set", "disable"].indexOf(action) < 0) return false
        if (action === "set" && (!Number.isInteger(value) || value < 1000 || value > 20000)) return false
        let args = ["python3", helper, action]
        if (action === "set") args.push(String(value))
        process.command = args
        busy = true
        process.running = true
        return true
    }
    onActiveChanged: { if (active) request("read"); else available = false }
    property var processObject: Process {
        id: process
        stdout: StdioCollector { id: output }
        stderr: StdioCollector { id: errors }
        onRunningChanged: if (!running && root.busy) { root.busy = false; root.available = false; root.error = "Night-light helper unavailable"; root.completed(false) }
        onExited: function(exitCode, exitStatus) {
            root.busy = false
            if (exitCode !== 0 || exitStatus !== 0) { root.available = false; root.error = errors.text.slice(0, 500); root.completed(false); return }
            try {
                let state = JSON.parse(output.text)
                if (typeof state.enabled !== "boolean" || !Number.isInteger(state.temperature) || state.temperature < 1000 || state.temperature > 20000) throw new Error("invalid state")
                root.enabled = state.enabled; root.temperature = state.temperature; root.available = root.active; root.error = ""; root.completed(true)
            } catch (e) { root.available = false; root.error = "Invalid night-light response"; root.completed(false) }
        }
    }
}
