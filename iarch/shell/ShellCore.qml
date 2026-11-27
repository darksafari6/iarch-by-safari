// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Shared session and isolated-preview shell core. UNTESTED-LIVE.
import QtQuick
import Quickshell
import "services" as Services
import "runtime" as Runtime

ShellRoot {
    id: shell
    property string repository: String(Quickshell.env("IARCH_SHELL_ROOT") || "")
    property bool preview: false
    property var performance: Services.Performance { }
    property var surfaceRegistry: Runtime.SurfaceRegistry { id: registry }
    property var themeRuntime: Runtime.ThemeRuntime { id: themeRuntime; surfaceRegistry: registry }
    property var sounds: Services.Sounds { helper: repository ? repository + "/iarch/cli/shell_sound.py" : ""; themeId: themeRuntime.activeId }
    function shown(name) {
        let surface = registry.surfaces[name]
        return !!surface && surface.available && surface.visible
    }
    property var clock: Services.Clock { id: clock; active: shell.shown("bar") || shell.shown("sidebar-left") }
    property var surfaceHost: Services.SurfaceHost {
        registry: registry
        preview: shell.preview
        services: ({clock: clock, battery: battery, network: network, audio: audio, media: media, stats: stats, todo: todo})
        themeRuntime: themeRuntime
    }
    property var surfaceIpc: Services.SurfaceIpc { registry: registry }
    // Deliberately disabled unless explicitly opted in; shell switch remains guarded.
    property var notificationLoader: LazyLoader {
        active: !shell.preview && Quickshell.env("IARCH_ENABLE_NOTIFICATIONS") === "1"
        Services.Notifications { helper: repository ? repository + "/iarch/cli/shell_notifications.py" : "" }
    }
    property var stats: Services.Stats {
        id: stats
        helper: repository ? repository + "/iarch/cli/shell_stats.py" : ""
        active: shell.shown("sidebar-right")
    }
    property string configDirectory: String(Quickshell.env("IARCH_CONFIG_DIR") || ((Quickshell.env("HOME") || "") + "/.config/iarch"))
    property var gameMode: Services.GameMode { id: gameMode; path: configDirectory.startsWith("/") ? configDirectory + "/settings.json" : "" }
    property var gameQualityBinding: Binding { target: Runtime.Theme; property: "gameMode"; value: gameMode.active }
    property var reduceMotionBinding: Binding { target: Runtime.Theme; property: "systemReduceMotion"; value: gameMode.reduceMotion }
    property var battery: Services.Battery { id: battery }
    property var batteryQualityBinding: Binding {
        target: Runtime.Theme
        property: "lowBattery"
        value: battery.low
    }
    property var todo: Services.Todo { id: todo; helper: repository ? repository + "/iarch/cli/shell_store_cli.py" : ""; active: shell.shown("sidebar-left") }
    property var timer: Services.TimerService { helper: repository ? repository + "/iarch/cli/shell_store_cli.py" : ""; active: false }
    property var stopwatch: Services.Stopwatch { helper: repository ? repository + "/iarch/cli/shell_store_cli.py" : ""; active: false }
    property var compositor: Services.Compositor { active: false }
    property var keyboard: Services.Keyboard { active: false }
    property var inputToggles: Services.InputToggles { helper: repository ? repository + "/iarch/cli/shell_input.py" : ""; active: false }
    property var idle: Services.Idle { active: false }
    property var screenshot: Services.Screenshot { helper: repository ? repository + "/iarch/cli/shell_screenshot.py" : "" }
    property var recorder: Services.Recorder { helper: repository ? repository + "/iarch/cli/shell_recorder.py" : "" }
    property var nightLight: Services.NightLight { helper: repository ? repository + "/iarch/cli/shell_night_light.py" : ""; active: false }
    property var visualizer: Services.Visualizer { configPath: repository ? repository + "/iarch/shell/services/cava.ini" : ""; active: false }
    property var audio: Services.Audio { id: audio; active: shell.shown("sidebar-right") }
    property var media: Services.Media { id: media; active: shell.shown("sidebar-right") }
    property var brightness: Services.Brightness { active: false }
    property var bluetooth: Services.Bluetooth { active: false }
    property var network: Services.Network {
        id: network
        helper: repository ? repository + "/iarch/cli/shell_network.py" : ""
        active: shell.shown("bar") || shell.shown("sidebar-right")
    }
    property var themeBridge: Services.ThemeBridge {
        id: bridge
        helper: repository ? repository + "/iarch/cli/shell_projection.py" : ""
        runtime: themeRuntime
    }
    property var startupTheme: Services.StartupTheme {
        helper: repository ? repository + "/iarch/cli/shell_projection.py" : ""
        referencePreview: shell.preview
        runtime: themeRuntime
        bridge: bridge
    }
}
