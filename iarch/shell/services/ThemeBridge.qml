// Copyright (C) 2026 Safari — GPL-3.0-or-later
// UNTESTED-LIVE: two-phase IPC prevents a timed-out validation applying later.
import QtQuick
import Quickshell.Io

QtObject {
    id: root
    property string helper: ""
    property var runtime: null
    property int sequence: 0
    property string token: ""
    property string requestedId: ""
    property string state: "idle"
    property var candidate: null
    property bool immediate: false
    property bool commitWhenReady: false

    function prepare(themeId, noTransition) {
        if (!helper || !runtime || process.running || !/^[a-z][a-z0-9]*(-[a-z0-9]+)*$/.test(themeId) || themeId.length > 120)
            return "rejected"
        sequence = (sequence % 1000000000) + 1
        token = String(sequence)
        requestedId = themeId
        candidate = null
        state = "pending"
        immediate = noTransition
        commitWhenReady = false
        process.command = ["python3", helper, themeId]
        process.running = true
        return "pending:" + token
    }
    // Queues a fresh validation of the last accepted pack; failure preserves it.
    function reload() {
        if (!runtime || !runtime.ready) return false
        let result = prepare(runtime.activeId, false)
        if (!result.startsWith("pending:")) return false
        commitWhenReady = true
        return true
    }
    function query(requestToken) {
        return requestToken === token ? state : "unknown"
    }
    function commit(requestToken) {
        if (requestToken !== token || state !== "ready" || !candidate) return false
        let bundle = candidate
        candidate = null
        state = "consumed"
        return runtime.acceptBundle(bundle, immediate)
    }
    property var process: Process {
        id: process
        stdout: StdioCollector { id: output }
        stderr: StdioCollector { id: errorOutput }
        onRunningChanged: {
            // FailedToStart emits runningChanged but not exited upstream.
            if (!running && root.state === "pending") root.state = "failed"
        }
        onExited: function(exitCode, exitStatus) {
            if (exitCode !== 0 || exitStatus !== 0) {
                root.state = "failed"
                return
            }
            try {
                let bundle = JSON.parse(output.text)
                if (!root.runtime.validBundle(bundle) || bundle.theme.id !== root.requestedId) {
                    root.state = "failed"
                    return
                }
                root.candidate = bundle
                root.state = "ready"
                if (root.commitWhenReady) {
                    root.commitWhenReady = false
                    if (!root.commit(root.token)) root.state = "failed"
                }
            } catch (e) { root.state = "failed" }
        }
    }
    property var ipc: IpcHandler {
        target: "iarch.theme"
        function apply(themeId: string): string { return root.prepare(themeId, false) }
        function applyImmediate(themeId: string): string { return root.prepare(themeId, true) }
        function status(requestToken: string): string { return root.query(requestToken) }
        function commit(requestToken: string): bool { return root.commit(requestToken) }
        function ping(): bool { return root.runtime !== null && root.helper !== "" }
        // Returns whether a reload was queued; status remains observable by IPC.
        function reload(): bool { return root.reload() }
    }
}
