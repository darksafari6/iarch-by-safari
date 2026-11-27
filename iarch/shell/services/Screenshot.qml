// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Explicit screen/region capture only; never captures in the background.
// UNTESTED-LIVE.
import QtQuick
import Quickshell.Io

QtObject {
    id: root
    property string helper: ""
    property bool available: helper !== ""
    property bool busy: false
    property string error: ""
    property string lastPath: ""
    signal completed(bool success, string path)
    function capture(mode) {
        if (!available || busy || (mode !== "screen" && mode !== "region")) return false
        busy = true
        process.command = ["python3", helper, mode]
        process.running = true
        return true
    }
    property var processObject: Process {
        id: process
        stdout: StdioCollector { id: output }
        stderr: StdioCollector { id: errors }
        onRunningChanged: if (!running && root.busy) { root.busy = false; root.error = "Screenshot helper unavailable"; root.completed(false, "") }
        onExited: function(exitCode, exitStatus) {
            root.busy = false
            if (exitCode !== 0 || exitStatus !== 0) { root.error = errors.text.slice(0, 500); root.completed(false, ""); return }
            try {
                let result = JSON.parse(output.text)
                if (typeof result.path !== "string" || !result.path.startsWith("/") || result.path.length > 4096) throw new Error("invalid path")
                root.lastPath = result.path; root.error = ""; root.completed(true, result.path)
            } catch (e) { root.error = "Invalid screenshot response"; root.completed(false, "") }
        }
    }
}
