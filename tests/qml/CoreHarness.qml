// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Tests core bindings against synthetic Quickshell types; never starts a session.
import QtQuick
import "../../iarch/shell" as Shell

Item {
    id: root
    property var core: Shell.ShellCore { id: core; preview: true }
    function exercise(text) {
        if (!core.preview || core.notificationLoader.active || !core.surfaceHost.preview) return "preview isolation failed"
        if (!core.themeRuntime.acceptBundle(JSON.parse(text), true)) return "reference bundle rejected"
        if (!core.surfaceHost.barLoader.activeAsync || !core.clock.active || !core.network.active) return "bar demand missing"
        if (core.stats.active || core.todo.active) return "hidden sidebar polling enabled"
        if (!core.surfaceRegistry.change("bar", "close")) return "close rejected"
        if (core.surfaceHost.barLoader.activeAsync || core.clock.active || core.network.active) return "bar demand not stopped"
        if (!core.surfaceRegistry.change("bar", "open")) return "reopen rejected"
        if (!core.surfaceHost.barLoader.activeAsync || !core.clock.active || !core.network.active) return "bar demand not restored"
        return "ok"
    }
}
