// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import "../../runtime" as Runtime

QtObject {
    id: root
    property var samples: []
    property var smoothed: []
    property bool active: false
    property real factor: 0.35
    function update() {
        let output = []
        let count = Math.min(128, samples.length)
        let alpha = Runtime.Theme.animationsEnabled ? Math.max(0, Math.min(1, factor)) : 1
        for (let i = 0; i < count; ++i) {
            let value = Math.max(0, Math.min(1, Number(samples[i]) || 0))
            let previous = Number(smoothed[i]) || 0
            output.push(previous + alpha * (value - previous))
        }
        smoothed = output
    }
    onSamplesChanged: if (!active || !Runtime.Theme.animationsEnabled) update()
    property Connections qualityChanges: Connections {
        target: Runtime.Theme
        function onAnimationsEnabledChanged() { if (!Runtime.Theme.animationsEnabled) root.update() }
    }
    property Timer timer: Timer {
        interval: Math.max(1, Math.round(1000 / Math.max(1, Runtime.Theme.spectrumFps)))
        repeat: true
        running: root.active && Runtime.Theme.animationsEnabled
        onTriggered: root.update()
    }
}
