// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Observes game mode and accessibility in the existing settings record.
// Never writes settings. UNTESTED-LIVE.
import QtQuick
import Quickshell.Io
import "game_mode.js" as Mode

QtObject {
    id: root
    property string path: ""
    property bool active: false
    property bool reduceMotion: false
    property bool available: false
    property string error: ""
    property var file: FileView {
        id: settings
        path: root.path
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            let value = Mode.parse(text())
            let motion = Mode.reduceMotion(text())
            // Each independent preference keeps its last valid value on error.
            if (value !== null) root.active = value
            if (motion !== null) root.reduceMotion = motion
            root.available = value !== null && motion !== null
            root.error = root.available ? "" : "Invalid shell preference record"
        }
        onLoadFailed: function(error) {
            if (error === FileViewError.FileNotFound) { root.active = false; root.reduceMotion = false }
            root.available = false
            root.error = "Cannot read game mode record"
        }
    }
}
