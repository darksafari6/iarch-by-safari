// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Logical surface state; actual lazy windows are delivered with the surfaces.
import QtQuick
import "registry.js" as Registry

QtObject {
    id: root
    property var surfaces: ({})
    property string error: ""
    signal surfaceChanged(string name, bool visible)

    function configure(layout) {
        let candidate = Registry.configure(layout, surfaces)
        if (candidate === null) {
            error = "invalid surface layout"
            return false
        }
        surfaces = candidate
        error = ""
        return true
    }

    function change(name, action) {
        let candidate = Registry.change(surfaces, name, action)
        if (candidate === null) {
            error = "unknown or disabled surface or action"
            return false
        }
        surfaces = candidate
        error = ""
        surfaceChanged(name, candidate[name].visible)
        return true
    }
}
