// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import "../../runtime" as Runtime

Item {
    id: root
    property bool shown: true
    property real initialScale: 0.9
    default property alias content: contentItem.data
    Item {
        id: contentItem
        anchors.fill: parent
        opacity: root.shown ? 1 : 0
        scale: root.shown || !Runtime.Theme.animationsEnabled ? 1 : root.initialScale
        Behavior on opacity { NumberAnimation { duration: Runtime.Theme.animationsEnabled ? Runtime.Theme.durationNormal : 0 } }
        Behavior on scale { NumberAnimation { duration: Runtime.Theme.animationsEnabled ? Runtime.Theme.durationNormal : 0; easing.type: Runtime.Theme.easing } }
    }
}
