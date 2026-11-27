// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import "../../runtime" as Runtime

Item {
    id: root
    property bool hovered: false
    property real distance: 4
    default property alias content: contentItem.data
    Item {
        id: contentItem
        anchors.fill: parent
        transform: Translate {
            y: root.hovered && Runtime.Theme.animationsEnabled ? -root.distance : 0
            Behavior on y { NumberAnimation { duration: Runtime.Theme.animationsEnabled ? Runtime.Theme.durationFast : 0; easing.type: Runtime.Theme.easing } }
        }
    }
}
