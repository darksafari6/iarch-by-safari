// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import "../../runtime" as Runtime

Rectangle {
    id: root
    property bool active: true
    implicitWidth: 160
    implicitHeight: 20
    color: Runtime.Theme.surface
    radius: Runtime.Theme.radiusSmall
    clip: true
    Rectangle {
        id: sheen
        width: Math.max(1, root.width / 3)
        height: root.height
        x: -width
        opacity: 0.45
        color: Runtime.Theme.outline
        SequentialAnimation on x {
            running: root.active && Runtime.Theme.animationsEnabled && root.visible
            loops: Animation.Infinite
            NumberAnimation { from: -sheen.width; to: root.width; duration: Runtime.Theme.durationNormal * 5; easing.type: Easing.Linear }
            PauseAnimation { duration: Runtime.Theme.durationFast * 2 }
        }
    }
}
