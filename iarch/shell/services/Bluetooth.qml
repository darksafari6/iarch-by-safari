// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Event-driven BlueZ adapter; no discovery without an explicit request.
// Setters request an asynchronous change, not a verified acknowledgement.
// UNTESTED-LIVE.
import QtQuick
import Quickshell.Bluetooth as BluetoothApi

QtObject {
    property bool active: false
    property var discoveryAdapter: null
    readonly property var adapter: BluetoothApi.Bluetooth.defaultAdapter
    readonly property bool available: active && adapter !== null
    readonly property string error: active && !available ? "Bluetooth adapter unavailable" : ""
    readonly property bool powered: available && adapter.enabled
    readonly property bool discovering: available && adapter.discovering
    readonly property var devices: available ? adapter.devices.values : []
    function setPowered(value) {
        if (!available || typeof value !== "boolean") return false
        adapter.enabled = value
        return true
    }
    function setDiscovery(value) {
        if (!available || typeof value !== "boolean") return false
        if (value) {
            if (discoveryAdapter && discoveryAdapter !== adapter) discoveryAdapter.discovering = false
            adapter.discovering = true
            discoveryAdapter = adapter
        } else {
            if (!discoveryAdapter) return false
            discoveryAdapter.discovering = false
            discoveryAdapter = null
        }
        return true
    }
    onActiveChanged: {
        if (!active && discoveryAdapter) {
            discoveryAdapter.discovering = false
            discoveryAdapter = null
        }
    }
    function setConnected(device, value) {
        if (!available || typeof value !== "boolean" || Array.from(devices).indexOf(device) < 0) return false
        device.connected = value
        return true
    }
}
