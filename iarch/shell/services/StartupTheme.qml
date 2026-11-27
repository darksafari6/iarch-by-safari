// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Load selected dynamic pack once, without racing an explicit IPC request.
// UNTESTED-LIVE.
import QtQuick
import Quickshell.Io

QtObject {
    id: root
    property string helper: ""
    // The bundled reference pack is for an isolated preview only.
    property bool referencePreview: false
    property var runtime: null
    property var bridge: null
    property string error: ""
    property var process: Process {
        id: reader
        command: root.referencePreview ? ["python3", root.helper, "--reference-preview"] : ["python3", root.helper]
        running: root.helper !== ""
        stdout: StdioCollector { id: output }
        stderr: StdioCollector { id: errors }
        onRunningChanged: if (!running && root.runtime && !root.runtime.ready && root.error === "") root.error = "Selected theme reader did not start"
        onExited: function(exitCode, exitStatus) {
            if (!root.runtime || !root.bridge || root.runtime.ready || root.bridge.state !== "idle") return
            if (exitCode !== 0 || exitStatus !== 0) { root.error = errors.text.slice(0, 500); return }
            try {
                if (!root.runtime.acceptBundle(JSON.parse(output.text), true)) root.error = root.runtime.error
            } catch (e) { root.error = "Invalid selected theme response" }
        }
    }
}
