// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick

LocalStore {
    id: root
    kind: "stopwatch"
    property real now: Date.now() / 1000
    readonly property real elapsed: (data.elapsed || 0) + (data.started_at ? Math.max(0, now - data.started_at) : 0)
    function start() { return request({action: "start"}) }
    function pause() { return request({action: "pause"}) }
    function reset() { return request({action: "reset"}) }
    property Timer ticker: Timer { interval: 1000; repeat: true; running: root.active; onTriggered: root.now = Date.now() / 1000 }
    onActiveChanged: { if (active) { now = Date.now() / 1000; request({action: "read"}) } }
}
