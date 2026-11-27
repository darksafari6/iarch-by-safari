// Copyright (C) 2026 Safari — GPL-3.0-or-later
// UNTESTED-LIVE: cached Wi-Fi and Linux network counters, sampled on demand.
import QtQuick
import Quickshell.Io
import "sample_validation.js" as Samples

QtObject {
    id: root
    property bool active: false
    property bool available: false
    property bool inFlight: false
    property string helper: ""
    property string error: ""
    property var networks: []
    property string ssid: ""
    property int signal: 0
    property real receivedPerSecond: 0
    property real transmittedPerSecond: 0
    property var previous: null
    property int interval: 5000
    function refresh() {
        if (active && helper && !reader.running) {
            reader.command = ["python3", helper]
            inFlight = true
            reader.running = true
        }
    }
    onActiveChanged: {
        if (active && !helper) { available = false; error = "Network helper is unavailable" }
        else if (active) refresh()
        else { inFlight = false; reader.running = false; previous = null; receivedPerSecond = 0; transmittedPerSecond = 0 }
    }
    property Timer timer: Timer {
        interval: Math.max(1000, root.interval)
        repeat: true
        running: root.active
        onTriggered: root.refresh()
    }
    property var process: Process {
        id: reader
        stdout: StdioCollector { id: output }
        onRunningChanged: {
            if (!running && root.inFlight) {
                root.inFlight = false
                root.available = false
                root.error = "Unable to start network reader"
            }
        }
        onExited: function(exitCode, exitStatus) {
            root.inFlight = false
            if (!root.active) return
            if (exitCode !== 0 || exitStatus !== 0) { root.available = false; root.error = "Network reader failed"; return }
            try {
                if (output.text.length > 1048576) throw new Error("sample too large")
                let value = JSON.parse(output.text)
                if (!Samples.network(value)) throw new Error("invalid sample")
                let rx = 0, tx = 0, elapsed = root.previous ? value.timestamp - root.previous.timestamp : 0
                if (elapsed > 0 && elapsed < 3600) {
                    for (let name of Object.keys(value.interfaces)) {
                        if (name === "lo" || !Object.prototype.hasOwnProperty.call(root.previous.interfaces, name)) continue
                        let current = value.interfaces[name], before = root.previous.interfaces[name]
                        rx += Math.max(0, current.rx - before.rx)
                        tx += Math.max(0, current.tx - before.tx)
                    }
                }
                root.receivedPerSecond = elapsed > 0 && elapsed < 3600 ? rx / elapsed : 0
                root.transmittedPerSecond = elapsed > 0 && elapsed < 3600 ? tx / elapsed : 0
                root.previous = value
                root.networks = value.networks
                let current = value.networks.find(function(network) { return network.active })
                root.ssid = current ? current.ssid : ""
                root.signal = current ? current.signal : 0
                root.available = value.available === true
                root.error = value.error || ""
            } catch (e) { root.available = false; root.error = "Invalid network sample" }
        }
    }
}
