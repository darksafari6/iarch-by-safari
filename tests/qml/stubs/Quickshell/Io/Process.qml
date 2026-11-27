// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Test double only: never launches or signals a process.
import QtQuick
QtObject {
    property bool running: false
    property bool stdinEnabled: false
    property var command: []
    property var stdout: null
    property var stderr: null
    property string written: ""
    property int lastSignal: 0
    signal started()
    signal exited(int exitCode, int exitStatus)
    function write(text) { written += text }
    function signal(value) { lastSignal = value }
}
