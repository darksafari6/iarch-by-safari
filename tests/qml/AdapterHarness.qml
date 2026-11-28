// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Test harness with synthetic Quickshell.Io types; not a compositor or IPC test.
import QtQuick
import Quickshell.Services.Pipewire as PipewireStub
import "../../iarch/shell/runtime" as Runtime
import "../../iarch/shell/services" as Services

Item {
    id: root
    property var registry: Runtime.SurfaceRegistry { id: registry }
    property var runtime: Runtime.ThemeRuntime { id: runtime; surfaceRegistry: registry }
    property var bridge: Services.ThemeBridge { id: bridge; helper: "/fake/helper"; runtime: runtime }
    property var surfaceIpc: Services.SurfaceIpc { id: surfaces; registry: registry }
    property var preferences: Services.GameMode { id: preferences }
    property var store: Services.LocalStore { id: store; helper: "/fake/helper"; kind: "timer" }
    property var stats: Services.Stats { id: stats; helper: "/fake/stats" }
    property var network: Services.Network { id: network; helper: "/fake/network" }
    property var brightness: Services.Brightness { id: brightness }
    property var audio: Services.Audio { id: audio }
    property var input: Services.InputToggles { id: input; helper: "/fake/input" }
    property var nightLight: Services.NightLight { id: nightLight; helper: "/fake/night-light" }
    property bool recordingSuccess: false
    property string recordingPath: ""
    property int recordingCompletions: 0
    property var recorder: Services.Recorder {
        id: recorder
        helper: "/fake/recorder"
        onCompleted: function(success, path) {
            root.recordingSuccess = success; root.recordingPath = path; root.recordingCompletions += 1
        }
    }

    function exercise(text) {
        let bundle = JSON.parse(text)
        let first = bridge.prepare(bundle.theme.id, false)
        if (!first.startsWith("pending:")) return "prepare rejected"
        let token = first.slice(8)
        bridge.process.stdout.text = JSON.stringify(bundle)
        bridge.process.exited(0, 0)
        bridge.process.running = false
        if (bridge.query(token) !== "ready" || !bridge.commit(token) || !runtime.ready) return "theme commit failed"
        if (!registry.surfaces.bar.visible || !surfaces.ipc.close("bar") || registry.surfaces.bar.visible) return "surface close failed"
        if (!surfaces.ipc.toggle("bar") || !registry.surfaces.bar.visible || surfaces.ipc.open("invalid")) return "surface validation failed"
        let goodId = runtime.activeId
        let second = bridge.prepare(bundle.theme.id, false)
        if (!second.startsWith("pending:")) return "second prepare rejected"
        bundle.theme.palette.background = "invalid"
        bridge.process.stdout.text = JSON.stringify(bundle)
        bridge.process.exited(0, 0)
        bridge.process.running = false
        if (bridge.query(second.slice(8)) !== "failed" || runtime.activeId !== goodId) return "invalid theme not rejected"
        let third = bridge.prepare(goodId, false)
        if (!third.startsWith("pending:")) return "third prepare rejected"
        bridge.process.running = false // Simulated FailedToStart: no exited signal.
        if (bridge.query(third.slice(8)) !== "failed") return "start failure not reported"

        preferences.file.fixtureText = '{"modes":{"game":{"active":true}},"animation":{"reduce_motion":true}}'
        preferences.file.loaded()
        if (!preferences.active || !preferences.reduceMotion || !preferences.available) return "preferences not read"
        preferences.file.fixtureText = '{"modes":{"game":{"active":"bad"}},"animation":{"reduce_motion":false}}'
        preferences.file.loaded()
        if (!preferences.active || preferences.reduceMotion || preferences.available) return "malformed preferences not isolated"
        preferences.file.loadFailed(2) // FileNotFound in the pinned API.
        if (preferences.active || preferences.reduceMotion) return "missing preferences not reset"

        if (!store.request({action: "read"}) || !store.busy) return "store request not started"
        store.child.started()
        if (store.child.written !== '{"action":"read"}' || store.child.stdinEnabled) return "store stdin incorrect"
        store.child.stdout.text = '{"schema_version":1,"remaining":12,"deadline":null}'
        store.child.exited(0, 0)
        store.child.running = false
        if (!store.available || store.busy || store.data.remaining !== 12) return "store response failed"
        if (!store.request({action: "read"})) return "second store request rejected"
        store.child.running = false // Simulated FailedToStart.
        if (store.busy || store.available || !store.error) return "store startup failure not reported"

        stats.active = true
        stats.process.stdout.text = '{"cpu":[100,50],"memory":null,"disk":null,"temperature":null,"errors":{}}'
        stats.process.exited(0, 0); stats.process.running = false
        if (!stats.available || stats.cpuPercent !== -1) return "first statistics sample failed"
        stats.refresh()
        stats.process.stdout.text = '{"cpu":[200,75],"memory":null,"disk":null,"temperature":null,"errors":{}}'
        stats.process.exited(0, 0); stats.process.running = false
        if (stats.cpuPercent !== 75) return "CPU delta incorrect"
        stats.refresh()
        stats.process.stdout.text = '{"errors":{}}'
        stats.process.exited(0, 0); stats.process.running = false
        if (stats.available || stats.error !== "Invalid statistics sample") return "bad statistics accepted"
        stats.active = false
        if (stats.timer.running || stats.cpuPercent !== -1) return "statistics polling not paused"

        network.active = true
        network.process.stdout.text = '{"timestamp":1,"interfaces":{"wlan0":{"rx":100,"tx":200}},"networks":[{"active":true,"ssid":"Home","signal":70}],"available":true,"error":null}'
        network.process.exited(0, 0); network.process.running = false
        if (!network.available || network.ssid !== "Home") return "network sample failed"
        network.refresh()
        network.process.stdout.text = '{"timestamp":3,"interfaces":{"wlan0":{"rx":300,"tx":260}},"networks":[],"available":true,"error":null}'
        network.process.exited(0, 0); network.process.running = false
        if (network.receivedPerSecond !== 100 || network.transmittedPerSecond !== 30) return "network delta incorrect"
        network.refresh()
        network.process.stdout.text = '{"timestamp":4,"interfaces":{"wlan0":{"rx":"bad","tx":1}},"networks":[],"available":true,"error":null}'
        network.process.exited(0, 0); network.process.running = false
        if (network.available || network.error !== "Invalid network sample") return "bad network sample accepted"
        network.active = false
        if (network.timer.running || network.receivedPerSecond !== 0) return "network polling not paused"

        brightness.active = true
        brightness.readProcess.stdout.text = 'panel,backlight,40,40%,100'
        brightness.readProcess.exited(0, 0); brightness.readProcess.running = false
        if (!brightness.available || brightness.percent !== 40 || !brightness.setPercent(25)) return "brightness read or write failed"
        if (brightness.writeProcess.command[3] !== '25' || brightness.setPercent(0)) return "brightness write validation failed"
        brightness.writeProcess.exited(0, 0); brightness.writeProcess.running = false
        if (!brightness.readProcess.running) return "brightness refresh missing"
        brightness.active = false

        input.active = true
        input.processObject.stdout.text = '{"pointers":["mouse-1"]}'
        input.processObject.exited(0, 0); input.processObject.running = false
        if (!input.available || input.pointers[0] !== "mouse-1") return "input list failed"
        if (!input.setDevice("mouse-1", false)) return "input request rejected"
        input.requestTimeout.triggered()
        if (input.busy || input.available || input.error.indexOf("timed out") < 0) return "input timeout failed"
        input.processObject.exited(0, 0) // Late exit cannot replace the timeout result.
        if (input.error.indexOf("timed out") < 0) return "input late response accepted"
        input.active = false

        nightLight.active = true
        nightLight.processObject.stdout.text = '{"enabled":true,"temperature":4200}'
        nightLight.processObject.exited(0, 0); nightLight.processObject.running = false
        if (!nightLight.available || nightLight.temperature !== 4200) return "night-light read failed"
        if (!nightLight.request("set", 5000)) return "night-light request rejected"
        nightLight.requestTimeout.triggered()
        if (nightLight.busy || nightLight.available || nightLight.error.indexOf("timed out") < 0) return "night-light timeout failed"
        nightLight.processObject.exited(0, 0)
        if (nightLight.error.indexOf("timed out") < 0) return "night-light late response accepted"
        nightLight.active = false

        let sink = {ready: true, isStream: false, audio: {volume: 0.5, muted: false}}
        let source = {ready: true, isStream: false, audio: {volume: 0.4, muted: false}}
        let stream = {ready: true, isStream: true, audio: {volume: 0.7, muted: false}}
        let stranger = {ready: true, isStream: true, audio: {volume: 0.2, muted: false}}
        PipewireStub.Pipewire.ready = true
        PipewireStub.Pipewire.defaultAudioSink = sink
        PipewireStub.Pipewire.defaultAudioSource = source
        PipewireStub.Pipewire.nodes = {values: [sink, source, stream]}
        audio.active = true
        if (!audio.available || audio.streams.length !== 1 || audio.tracker.objects.length !== 3) return "audio streams not tracked"
        if (!audio.microphoneAvailable || audio.microphoneVolume !== 0.4 || !audio.setMicrophoneVolume(0.8) || !audio.setMicrophoneMuted(true)) return "microphone control failed"
        if (source.audio.volume !== 0.8 || !source.audio.muted || audio.setMicrophoneVolume(NaN) || audio.setMicrophoneVolume(2)) return "microphone validation failed"
        if (!audio.setStreamVolume(stream, 0.3) || !audio.setStreamMuted(stream, true) || stream.audio.volume !== 0.3 || !stream.audio.muted) return "stream control failed"
        if (audio.setStreamVolume(stranger, 0.4) || audio.setStreamVolume(stream, 2) || audio.setStreamMuted(stream, "yes")) return "invalid stream control accepted"
        PipewireStub.Pipewire.ready = false
        if (audio.microphoneAvailable || audio.setMicrophoneVolume(0.5) || audio.setStreamMuted(stream, false)) return "unready audio accepted"
        audio.active = false
        if (audio.tracker.objects.length !== 0 || audio.setStreamMuted(stream, false)) return "audio tracking not stopped"

        if (!recorder.start() || !recorder.stop() || !recorder.stopRequested || recorder.state !== "starting") return "early recorder stop rejected"
        recorder.processObject.stdout.read('{"status":"started"}')
        if (recorder.state !== "stopping" || recorder.processObject.lastSignal !== 2) return "early recorder stop not delivered"
        recorder.processObject.stdout.read('{"status":"finished","path":"/private/test.mkv"}')
        recorder.processObject.exited(0, 0); recorder.processObject.running = false
        if (!root.recordingSuccess || root.recordingPath !== "/private/test.mkv" || root.recordingCompletions !== 1) return "recording completion failed"
        if (!recorder.start()) return "second recorder start rejected"
        recorder.startupTimeout.triggered()
        if (recorder.state !== "idle" || recorder.error !== "Recorder startup timed out" || root.recordingCompletions !== 2 || root.recordingSuccess) return "recorder startup timeout failed"
        return "ok"
    }
}
