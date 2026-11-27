// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Native event-driven PipeWire adapter. UNTESTED-LIVE.
import QtQuick
import Quickshell.Services.Pipewire

QtObject {
    id: root
    property bool active: false
    readonly property var sink: Pipewire.defaultAudioSink
    readonly property var source: Pipewire.defaultAudioSource
    readonly property bool available: active && Pipewire.ready && sink !== null && sink.ready && sink.audio !== null
    readonly property string error: available ? "" : (active ? "Audio output unavailable" : "")
    readonly property real volume: available ? sink.audio.volume : 0
    readonly property bool muted: available ? sink.audio.muted : false
    readonly property bool microphoneAvailable: active && source !== null && source.ready && source.audio !== null
    readonly property bool microphoneMuted: microphoneAvailable ? source.audio.muted : false
    readonly property var nodes: active ? Pipewire.nodes.values : []
    readonly property var streams: Array.from(nodes).filter(function(node) { return node && node.isStream && node.audio !== null })
    // Stream volume, mute and metadata require a bound node too, not just the
    // default sink/source. Release all bindings when the consumer is hidden.
    property var tracker: PwObjectTracker { objects: root.active ? [root.sink, root.source].concat(root.streams) : [] }
    function setVolume(value) {
        if (!available || typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) return false
        sink.audio.volume = value
        return true
    }
    function setMuted(value) {
        if (!available || typeof value !== "boolean") return false
        sink.audio.muted = value
        return true
    }
    function setMicrophoneMuted(value) {
        if (!microphoneAvailable || typeof value !== "boolean") return false
        source.audio.muted = value
        return true
    }
    function streamReady(stream) {
        return active && streams.indexOf(stream) >= 0 && stream.ready && stream.audio !== null
    }
    function setStreamVolume(stream, value) {
        if (!streamReady(stream) || typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) return false
        stream.audio.volume = value
        return true
    }
    function setStreamMuted(stream, value) {
        if (!streamReady(stream) || typeof value !== "boolean") return false
        stream.audio.muted = value
        return true
    }
}
