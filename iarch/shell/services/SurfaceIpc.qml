// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Logical state requests; showing an actual window is not a verified IPC ack.
// UNTESTED-LIVE.
import QtQuick
import Quickshell.Io

QtObject {
    id: root
    property var registry: null
    property var ipc: IpcHandler {
        target: "iarch.surface"
        function toggle(name: string): bool { return root.registry ? root.registry.change(name, "toggle") : false }
        function open(name: string): bool { return root.registry ? root.registry.change(name, "open") : false }
        function close(name: string): bool { return root.registry ? root.registry.change(name, "close") : false }
    }
}
