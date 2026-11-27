// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Explicit pointer selection only; requests are asynchronous, not verified state.
// UNTESTED-LIVE. Raw mode can cause cursor desynchronization.
import QtQuick
import Quickshell.Io

QtObject {
    id: root
    property bool active: false
    property string helper: ""
    property bool available: false
    property bool busy: false
    property string error: ""
    property var pointers: []
    property string operation: ""
    signal completed(bool success, bool verified)
    function run(args) {
        if (!active || !helper || busy) return false
        operation = args[0]
        process.command = ["python3", helper].concat(args)
        busy = true; process.running = true
        return true
    }
    function refresh() { return run(["list"]) }
    function setDevice(name, enabled) {
        if (typeof name !== "string" || typeof enabled !== "boolean" || pointers.indexOf(name) < 0) return false
        return run(["device", enabled ? "on" : "off", name])
    }
    function setRaw(enabled) {
        if (typeof enabled !== "boolean") return false
        return run(["raw", enabled ? "on" : "off"])
    }
    onActiveChanged: { if (active) refresh(); else available = false }
    property var processObject: Process {
        id: process
        stdout: StdioCollector { id: output }
        stderr: StdioCollector { id: errors }
        onRunningChanged: if (!running && root.busy) { root.busy = false; root.available = false; root.error = "Input helper unavailable"; root.completed(false, false) }
        onExited: function(exitCode, exitStatus) {
            root.busy = false
            if (exitCode !== 0 || exitStatus !== 0) { root.available = false; root.error = errors.text.slice(0, 500); root.completed(false, false); return }
            try {
                let data = JSON.parse(output.text)
                if (root.operation === "list") {
                    if (!Array.isArray(data.pointers) || !data.pointers.every(function(n) { return typeof n === "string" })) throw new Error("invalid list")
                    root.pointers = data.pointers
                } else if (data.requested !== true || data.verified !== false) throw new Error("invalid result")
                root.available = root.active; root.error = ""; root.completed(true, false)
            } catch (e) { root.available = false; root.error = "Invalid input response"; root.completed(false, false) }
        }
    }
}
