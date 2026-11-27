// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick

LocalStore {
    id: root
    kind: "timer"
    property real now: Date.now() / 1000
    readonly property real remaining: data.deadline ? Math.max(0, data.deadline - now) : (data.remaining || 0)
    function setSeconds(seconds) { return typeof seconds === "number" && Number.isFinite(seconds) && seconds >= 0 && seconds < 1e9 && request({action: "set", seconds: seconds}) }
    function start() { return request({action: "start"}) }
    function pause() { return request({action: "pause"}) }
    function reset() { return request({action: "reset"}) }
    property Timer ticker: Timer { interval: 1000; repeat: true; running: root.active; onTriggered: root.now = Date.now() / 1000 }
    onActiveChanged: { if (active) { now = Date.now() / 1000; request({action: "read"}) } }
}
