// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Local clock adapter. Polls only while a consumer marks it active.
import QtQuick
import "calendar.js" as Calendar

QtObject {
    id: root
    readonly property bool available: true
    readonly property string error: ""
    property bool active: false
    property date now: new Date()
    readonly property string timeText: Qt.formatTime(now, "HH:mm")
    readonly property var monthModel: Calendar.month(now.getFullYear(), now.getMonth(), now)
    readonly property string dateText: Qt.formatDate(now, "dddd, d MMMM yyyy")
    property Timer refreshTimer: Timer {
        interval: 1000
        repeat: true
        running: root.active
        onTriggered: root.now = new Date()
    }
    onActiveChanged: if (active) now = new Date()
}
