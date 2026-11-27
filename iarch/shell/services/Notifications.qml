// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Optional notification server. Never load alongside another desktop server.
// Persistence helper receives bounded records over stdin. UNTESTED-LIVE.
import QtQuick
import Quickshell.Io
import Quickshell
import Quickshell.Services.Notifications
import "notification_groups.js" as Groups

QtObject {
    id: root
    property string helper: ""
    property bool available: false
    property string error: "Notification server ownership is unverified"
    property bool ownerBusy: false
    property var queue: []
    property bool inFlight: false
    // Only a consumer that really provides action buttons/image rendering may opt in.
    property bool actionsVisible: false
    property bool imagesVisible: false
    property bool historyBusy: false
    property var history: []
    readonly property var notifications: server.trackedNotifications.values
    readonly property var groups: Groups.group(Array.from(notifications))
    readonly property int count: notifications.length
    function invoke(notification, action) {
        if (!actionsVisible || Array.from(notifications).indexOf(notification) < 0 ||
            Array.from(notification.actions).indexOf(action) < 0) return false
        action.invoke()
        return true
    }
    function refreshOwner() {
        if (!helper || ownerBusy) return false
        ownerBusy = true
        ownerReader.command = ["python3", helper, "owner", "--pid", String(Quickshell.processId)]
        ownerReader.running = true
        return true
    }
    function refreshHistory() {
        if (!helper || historyBusy) return false
        historyBusy = true
        historyReader.command = ["python3", helper, "read"]
        historyReader.running = true
        return true
    }
    signal received(var notification)
    function enqueue(notification) {
        if (!helper || notification.transient || notification.lastGeneration) return
        let urgency = notification.urgency === NotificationUrgency.Critical ? "critical" :
                      notification.urgency === NotificationUrgency.Low ? "low" : "normal"
        let actions = Array.from(notification.actions).slice(0, 20).map(function(action) {
            return {id: String(action.identifier).slice(0, 200), label: String(action.text).slice(0, 200)}
        }).filter(function(action) { return action.id.length > 0 && action.label.length > 0 })
        let item = {app: String(notification.appName || "").slice(0, 200),
                    summary: String(notification.summary || "").slice(0, 1000),
                    body: String(notification.body || "").slice(0, 4000),
                    urgency: urgency, timestamp: Date.now() / 1000,
                    image: String(notification.image || "").slice(0, 2048), actions: actions}
        if (queue.length >= 50) { error = "Notification history queue is full"; return }
        queue = queue.concat([item])
        drain()
    }
    function drain() {
        if (writer.running || queue.length === 0 || !helper) return
        writer.command = ["python3", helper, "append"]
        writer.stdinEnabled = true
        inFlight = true
        writer.running = true
    }
    property var serverObject: NotificationServer {
        id: server
        bodyMarkupSupported: false
        bodyHyperlinksSupported: false
        persistenceSupported: true
        actionsSupported: root.actionsVisible
        imageSupported: root.imagesVisible
        onNotification: function(notification) {
            notification.tracked = true
            if (server.trackedNotifications.values.length > 200) server.trackedNotifications.values[0].dismiss()
            root.enqueue(notification)
            root.received(notification)
        }
    }
    property Timer initialOwnerProbe: Timer { interval: 500; running: true; onTriggered: root.refreshOwner() }
    property var ownerProbe: Process {
        id: ownerReader
        stdout: StdioCollector { id: ownerOutput }
        onRunningChanged: if (!running && root.ownerBusy) { root.ownerBusy = false; root.available = false; root.error = "Notification ownership probe unavailable" }
        onExited: function(exitCode, exitStatus) {
            root.ownerBusy = false
            try {
                if (exitCode !== 0 || exitStatus !== 0) throw new Error("failed")
                let data = JSON.parse(ownerOutput.text)
                if (typeof data.available !== "boolean" || typeof data.error !== "string") throw new Error("invalid")
                root.available = data.available; root.error = data.error.slice(0, 500)
            } catch (e) { root.available = false; root.error = "Notification ownership probe failed" }
        }
    }
    property var historyReaderProcess: Process {
        id: historyReader
        stdout: StdioCollector { id: historyOutput }
        onRunningChanged: if (!running && root.historyBusy) { root.historyBusy = false; root.error = "Notification history unavailable" }
        onExited: function(exitCode, exitStatus) {
            root.historyBusy = false
            if (exitCode !== 0 || exitStatus !== 0) { root.error = "Notification history read failed"; return }
            try {
                let data = JSON.parse(historyOutput.text)
                if (!data || data.schema_version !== 1 || !Array.isArray(data.items) || data.items.length > 200) throw new Error("invalid history")
                root.history = data.items
            } catch (e) { root.error = "Invalid notification history" }
        }
    }
    property var historyWriter: Process {
        id: writer
        stdinEnabled: true
        stdout: StdioCollector { }
        stderr: StdioCollector { id: errors }
        onRunningChanged: if (!running && root.inFlight) {
            // FailedToStart emits runningChanged but not exited. Discard this
            // failed item so a missing helper cannot permanently wedge the queue.
            root.inFlight = false
            root.error = "Notification history helper unavailable"
            root.queue = root.queue.slice(1)
            Qt.callLater(root.drain)
        }
        onStarted: {
            write(JSON.stringify(root.queue[0]))
            stdinEnabled = false
        }
        onExited: function(exitCode, exitStatus) {
            root.inFlight = false
            if (exitCode !== 0 || exitStatus !== 0) root.error = "Notification history: " + errors.text.slice(0, 300)
            root.queue = root.queue.slice(1)
            Qt.callLater(root.drain)
        }
    }
}
