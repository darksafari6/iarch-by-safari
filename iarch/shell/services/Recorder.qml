// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Explicit recording; no microphone/audio recording. UNTESTED-LIVE.
import QtQuick
import Quickshell.Io

QtObject {
    id: root
    property string helper: ""
    property bool available: helper !== ""
    property string state: "idle" // idle, starting, recording, stopping
    property string error: ""
    property string lastPath: ""
    property bool startedEvent: false
    property bool stopRequested: false
    property bool startupTimedOut: false
    signal completed(bool success, string path)
    function start() {
        if (!available || state !== "idle") return false
        state = "starting"; error = ""; startedEvent = false; stopRequested = false; startupTimedOut = false; lastPath = ""
        process.command = ["python3", helper]
        startupTimeout.restart()
        process.running = true
        return true
    }
    function stop() {
        // Do not signal Python before it has installed its signal handler. A
        // starting request is delivered immediately after its startup event.
        if (state === "starting") { stopRequested = true; return true }
        if (state !== "recording") return false
        state = "stopping"
        process.signal(2) // SIGINT requests a graceful finalization.
        return true
    }
    property Timer startupTimeout: Timer {
        interval: 10000
        onTriggered: {
            if (root.state !== "starting") return
            root.startupTimedOut = true
            root.error = "Recorder startup timed out"
            process.running = false // SIGTERM; helper, if running, shuts down its child.
        }
    }
    property var processObject: Process {
        id: process
        stdout: SplitParser {
            onRead: function(line) {
                try {
                    let event = JSON.parse(line)
                    if (event.status === "started" && root.state === "starting" && !root.startupTimedOut) {
                        startupTimeout.stop()
                        root.startedEvent = true
                        root.state = "recording"
                        if (root.stopRequested) root.stop()
                    }
                    else if (event.status === "finished" && root.state === "stopping" && typeof event.path === "string" && event.path.startsWith("/") && event.path.length <= 4096) root.lastPath = event.path
                } catch (e) { root.error = "Invalid recorder response" }
            }
        }
        stderr: StdioCollector { id: errors }
        onRunningChanged: if (!running && root.state !== "idle") {
            startupTimeout.stop()
            root.state = "idle"
            if (!root.error) root.error = "Recorder helper unavailable"
            root.completed(false, "")
        }
        onExited: function(exitCode, exitStatus) {
            startupTimeout.stop()
            let ok = exitCode === 0 && exitStatus === 0 && root.state === "stopping" && root.lastPath !== ""
            root.state = "idle"
            if (!ok) root.error = root.error || errors.text.slice(0, 500) || "Recording failed"
            root.completed(ok, ok ? root.lastPath : "")
        }
    }
}
