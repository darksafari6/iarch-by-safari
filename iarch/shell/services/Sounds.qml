// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Only validated event IDs are accepted. A true return means queued, not played.
// UNTESTED-LIVE.
import QtQuick
import Quickshell.Io

QtObject {
    id: root
    property string helper: ""
    property string themeId: ""
    property bool available: helper !== "" && themeId !== ""
    property string error: ""
    property bool busy: false
    signal finished(bool played)
    function play(event) {
        if (!available || busy || ["notification", "volume", "switch"].indexOf(event) < 0) return false
        busy = true
        process.command = ["python3", helper, themeId, event]
        process.running = true
        return true
    }
    property var processObject: Process {
        id: process
        stdout: StdioCollector { id: output }
        stderr: StdioCollector { id: errors }
        onRunningChanged: if (!running && root.busy) { root.busy = false; root.error = "Sound helper unavailable"; root.finished(false) }
        onExited: function(exitCode, exitStatus) {
            root.busy = false
            if (exitCode !== 0 || exitStatus !== 0) { root.error = errors.text.slice(0, 500); root.finished(false); return }
            try {
                let result = JSON.parse(output.text)
                if (typeof result.played !== "boolean") throw new Error("invalid response")
                root.error = ""
                root.finished(result.played)
            } catch (e) { root.error = "Invalid sound response"; root.finished(false) }
        }
    }
    property var ipc: IpcHandler {
        target: "iarch.sound"
        function play(event: string): bool { return root.play(event) }
    }
}
