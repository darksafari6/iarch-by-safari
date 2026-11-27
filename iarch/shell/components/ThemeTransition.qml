// Copyright (C) 2026 Safari — GPL-3.0-or-later
// A brief, non-interactive overlay for theme changes. UNTESTED-LIVE.
import QtQuick
import "../runtime" as Runtime

Item {
    id: root
    property color oldColor: Runtime.Theme.background
    property string effect: "none"
    property real progress: 1
    visible: progress < 1 && Runtime.Theme.animationsEnabled
    enabled: false
    function play(style, previous) {
        animation.stop()
        if (!Runtime.Theme.animationsEnabled || (style !== "fade" && style !== "wipe")) { progress = 1; return }
        oldColor = previous; effect = style; progress = 0; animation.start()
    }
    Rectangle {
        width: root.effect === "wipe" ? root.width * (1 - root.progress) : root.width
        height: root.height
        color: root.oldColor
        opacity: root.effect === "fade" ? 1 - root.progress : 1
    }
    NumberAnimation { id: animation; target: root; property: "progress"; from: 0; to: 1; duration: 300; easing.type: Runtime.Theme.easing }
}
