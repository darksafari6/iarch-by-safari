// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Test double only: no filesystem access or watcher.
import QtQuick
QtObject {
    property string path: ""
    property bool watchChanges: false
    property bool printErrors: false
    property string fixtureText: ""
    signal fileChanged()
    signal loaded()
    signal loadFailed(int error)
    function text() { return fixtureText }
    function reload() { }
}
