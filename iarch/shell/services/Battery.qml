// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Event-driven UPower aggregate device. UNTESTED-LIVE.
import QtQuick
import Quickshell.Services.UPower

QtObject {
    readonly property var device: UPower.displayDevice
    readonly property bool available: device !== null && device !== undefined && device.ready && device.isLaptopBattery && device.isPresent
    readonly property string error: available ? "" : "Battery information unavailable"
    readonly property real percentage: available ? Math.max(0, Math.min(1, device.percentage)) : 0
    readonly property bool onBattery: available && UPower.onBattery
    readonly property bool low: onBattery && percentage <= 0.2
    readonly property bool charging: available && device.state === UPowerDeviceState.Charging
    readonly property real timeToEmpty: available ? device.timeToEmpty : 0
    readonly property real timeToFull: available ? device.timeToFull : 0
}
