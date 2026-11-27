// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Observe idle state only; no locking or power action is performed here.
// UNTESTED-LIVE; ext-idle-notify-v1 compositor support is required.
import QtQuick
import Quickshell.Wayland

QtObject {
    id: root
    property bool active: false
    property real timeoutSeconds: 300
    readonly property bool validTimeout: Number.isFinite(timeoutSeconds) && timeoutSeconds >= 1 && timeoutSeconds <= 86400
    readonly property bool available: active && validTimeout && monitor.enabled
    readonly property string error: !active ? "" : (!validTimeout ? "Invalid idle timeout" : (!available ? "Idle monitor unavailable" : ""))
    readonly property bool idle: available && monitor.isIdle
    property var monitorObject: IdleMonitor {
        id: monitor
        enabled: root.active && root.validTimeout
        timeout: root.validTimeout ? root.timeoutSeconds : 300
        respectInhibitors: true
    }
}
