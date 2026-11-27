// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import "../../runtime" as Runtime

Item {
    id: root
    property bool pressed: false
    property real pressedScale: 0.96
    default property alias content: contentItem.data
    Item {
        id: contentItem
        anchors.fill: parent
        scale: root.pressed && Runtime.Theme.animationsEnabled ? root.pressedScale : 1
        Behavior on scale { NumberAnimation { duration: Runtime.Theme.animationsEnabled ? Runtime.Theme.durationFast : 0; easing.type: Runtime.Theme.easing } }
    }
}
