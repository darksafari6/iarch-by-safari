// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Opt-in animation-frame interval sample; disabled when not being measured.
// This is not GPU render duration or a reliable idle CPU benchmark. UNTESTED-LIVE.
import QtQuick
import Quickshell.Io

QtObject {
    id: root
    property bool sampling: false
    property int count: 0
    property real sumMs: 0
    property real maxMs: 0
    function start() {
        if (sampling) return false
        count = 0; sumMs = 0; maxMs = 0; sampling = true; limit.restart()
        return true
    }
    function finish() {
        sampling = false; limit.stop()
        return JSON.stringify({frames: count, average_ms: count ? sumMs / count : null, max_ms: count ? maxMs : null})
    }
    property FrameAnimation sampler: FrameAnimation {
        running: root.sampling
        onTriggered: {
            // Ignore the first frame: it is not an interval between two samples.
            if (currentFrame <= 1 || !Number.isFinite(frameTime) || frameTime <= 0 || frameTime > 10) return
            let ms = frameTime * 1000
            root.count += 1; root.sumMs += ms; root.maxMs = Math.max(root.maxMs, ms)
        }
    }
    property Timer limit: Timer { interval: 3000; onTriggered: root.sampling = false }
    property var ipc: IpcHandler {
        target: "iarch.performance"
        function start(): bool { return root.start() }
        function finish(): string { return root.finish() }
    }
}
