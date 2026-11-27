// Copyright (C) 2026 Safari — GPL-3.0-or-later
// One serialized helper operation, JSON through stdin, never a shell string.
// UNTESTED-LIVE.
import QtQuick
import Quickshell.Io

QtObject {
    id: root
    property bool active: false
    property string helper: ""
    property string kind: ""
    property bool available: false
    property string error: ""
    property bool busy: false
    property var data: ({})
    property var pending: ({})
    signal updated()
    signal recovered(string backupPath)
    // Explicit user action only; the helper preserves the corrupt file first.
    function recover() { return request({action: "recover"}) }
    function request(value) {
        if (!helper || busy || !value || typeof value !== "object") return false
        pending = value
        busy = true
        process.command = ["python3", helper, kind]
        process.stdinEnabled = true
        process.running = true
        return true
    }
    onActiveChanged: if (active) request({action: "read"})
    property var child: Process {
        id: process
        stdinEnabled: true
        stdout: StdioCollector { id: output }
        stderr: StdioCollector { id: errors }
        onRunningChanged: if (!running && root.busy) { root.busy = false; root.available = false; root.error = "Store helper unavailable" }
        onStarted: { write(JSON.stringify(root.pending)); stdinEnabled = false }
        onExited: function(exitCode, exitStatus) {
            root.busy = false
            if (exitCode !== 0 || exitStatus !== 0) { root.available = false; root.error = errors.text.slice(0, 500); return }
            try {
                let value = JSON.parse(output.text)
                if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("invalid response")
                let backup = ""
                if (root.pending.action === "recover") {
                    if (typeof value.backup !== "string" || !value.backup.startsWith("/") ||
                            !value.data || typeof value.data !== "object" || Array.isArray(value.data)) throw new Error("invalid recovery response")
                    backup = value.backup
                    value = value.data
                }
                root.data = value
                root.available = true
                root.error = ""
                root.updated()
                if (backup) root.recovered(backup)
            } catch (e) { root.available = false; root.error = "Invalid store response" }
        }
    }
}
