// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Raw local visualizer stream and a quiet no-tool fallback. UNTESTED-LIVE.
import QtQuick
import Quickshell.Io
import "../runtime" as Runtime
import "spectrum.js" as SpectrumParser

QtObject {
    id: root
    property bool active: false
    property string configPath: ""
    property bool available: false
    property string error: ""
    property var samples: []
    property real phase: 0
    property bool awaitingStart: false
    property real lastFrame: 0
    function start() {
        if (!active || !configPath || process.running) return
        awaitingStart = true
        process.command = ["cava", "-p", configPath]
        process.running = true
    }
    onActiveChanged: {
        if (active) start()
        else { awaitingStart = false; process.running = false; available = false; samples = [] }
    }
    property var stream: Process {
        id: process
        stdout: SplitParser {
            onRead: function(data) {
                let values = SpectrumParser.parse(data, 32, 1000)
                if (values === null) { root.available = false; root.error = "Invalid spectrum frame"; return }
                let now = Date.now()
                if (now - root.lastFrame < 1000 / Math.max(1, Runtime.Theme.spectrumFps)) return
                root.lastFrame = now
                root.samples = values
                root.available = true
                root.error = ""
            }
        }
        onStarted: root.awaitingStart = false
        onRunningChanged: if (!running && root.awaitingStart) { root.awaitingStart = false; root.available = false; root.error = "Visualizer unavailable" }
        onExited: function(exitCode, exitStatus) { root.available = false; if (root.active) root.error = "Visualizer stopped" }
    }
    property Timer fallback: Timer {
        interval: 1000 / Math.max(1, Runtime.Theme.spectrumFps)
        repeat: true
        running: root.active && !root.available && Runtime.Theme.animationsEnabled
        onTriggered: {
            root.phase += 0.1
            let frame = []
            for (let i = 0; i < 32; ++i) frame.push(0.03 + 0.025 * (1 + Math.sin(root.phase + i * 0.6)))
            root.samples = frame
        }
    }
}
