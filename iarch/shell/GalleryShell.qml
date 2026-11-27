// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Isolated preview; it never starts a notification server or session surfaces.
// UNTESTED-LIVE: Process and Window lifecycle require a real Quickshell session.
import QtQuick
import Quickshell
import Quickshell.Io
import "runtime" as Runtime

ShellRoot {
    id: root
    property string repository: String(Quickshell.env("IARCH_SHELL_ROOT") || "")
    property string helper: repository + "/iarch/cli/shell_projection.py"
    property var registry: Runtime.SurfaceRegistry { id: registry }
    property var runtime: Runtime.ThemeRuntime { id: themeRuntime; surfaceRegistry: registry }
    property var gallery: Gallery {
        id: gallery
        transitionRuntime: themeRuntime
        visible: true
        onClosing: Qt.quit()
        onThemeRequested: function(themeId) {
            if (!/^[a-z][a-z0-9]*(-[a-z0-9]+)*$/.test(themeId) || projection.running) {
                error = "Theme request is invalid or another request is running."
                return
            }
            error = ""
            projection.command = ["python3", root.helper, themeId === "dynamic-reference" ? "--reference-preview" : themeId]
            projection.running = true
        }
    }
    property var listProcess: Process {
        id: listProcess
        command: ["python3", root.helper, "--list"]
        running: root.repository !== ""
        stdout: StdioCollector { id: listOutput }
        stderr: StdioCollector { id: listError }
        onExited: function(exitCode, exitStatus) {
            if (exitCode !== 0 || exitStatus !== 0) {
                gallery.error = "Unable to list installed themes: " + listError.text.slice(0, 500)
                return
            }
            try {
                let names = JSON.parse(listOutput.text)
                if (!Array.isArray(names) || !names.every(function(x) { return typeof x === "string" && /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/.test(x) })) throw new Error("invalid catalogue")
                gallery.themes = ["dynamic-reference"].concat(names)
            } catch (e) { gallery.error = "Unable to parse theme catalogue." }
        }
    }
    property var projectionProcess: Process {
        id: projection
        stdout: StdioCollector { id: projectionOutput }
        stderr: StdioCollector { id: projectionError }
        onExited: function(exitCode, exitStatus) {
            if (exitCode !== 0 || exitStatus !== 0) {
                gallery.error = "Theme rejected: " + projectionError.text.slice(0, 500)
                return
            }
            try {
                if (!themeRuntime.acceptBundle(JSON.parse(projectionOutput.text))) gallery.error = themeRuntime.error
            } catch (e) { gallery.error = "Invalid theme response." }
        }
    }
}
