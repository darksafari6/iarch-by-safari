// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Event-driven MPRIS data; tick position only while a consumer is active.
// UNTESTED-LIVE. Art URLs are exposed as data and never fetched here.
import QtQuick
import Quickshell.Services.Mpris
import "media_selection.js" as Selection

QtObject {
    id: root
    property bool active: false
    property string preferredPlayer: ""
    readonly property var players: active ? Mpris.players.values : []
    readonly property var player: Selection.choose(players, preferredPlayer)
    readonly property bool available: active && player !== null
    readonly property string error: active && !available ? "No media player available" : ""
    readonly property string title: available ? player.trackTitle : ""
    readonly property string artist: available ? player.trackArtist : ""
    readonly property string album: available ? player.trackAlbum : ""
    readonly property string artUrl: available ? player.trackArtUrl : ""
    readonly property real position: available ? player.position : 0
    readonly property real length: available ? player.length : 0
    readonly property bool playing: available && player.isPlaying
    function toggle() { if (!available || !player.canTogglePlaying) return false; player.togglePlaying(); return true }
    function next() { if (!available || !player.canGoNext) return false; player.next(); return true }
    function previous() { if (!available || !player.canGoPrevious) return false; player.previous(); return true }
    function seek(seconds) {
        if (!available || !player.canSeek || !player.positionSupported || typeof seconds !== "number" ||
                !Number.isFinite(seconds) || seconds < 0 || (player.lengthSupported && seconds > player.length)) return false
        player.position = seconds
        return true
    }
    property Timer positionTimer: Timer {
        interval: 1000
        repeat: true
        running: root.active && root.available && root.playing
        onTriggered: root.player.positionChanged()
    }
}
