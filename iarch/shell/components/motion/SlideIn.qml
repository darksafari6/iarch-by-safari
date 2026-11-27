// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import "../../runtime" as Runtime

Item {
    id: root
    property bool shown: true
    property string edge: "left"
    property real distance: 24
    property bool fade: true
    default property alias content: contentItem.data
    Item {
        id: contentItem
        anchors.fill: parent
        opacity: root.shown || !root.fade ? 1 : 0
        transform: Translate {
            x: root.shown ? 0 : (root.edge === "left" ? -root.distance : (root.edge === "right" ? root.distance : 0))
            y: root.shown ? 0 : (root.edge === "top" ? -root.distance : (root.edge === "bottom" ? root.distance : 0))
            Behavior on x { NumberAnimation { duration: Runtime.Theme.animationsEnabled ? Runtime.Theme.durationNormal : 0; easing.type: Runtime.Theme.easing } }
            Behavior on y { NumberAnimation { duration: Runtime.Theme.animationsEnabled ? Runtime.Theme.durationNormal : 0; easing.type: Runtime.Theme.easing } }
        }
        Behavior on opacity { NumberAnimation { duration: Runtime.Theme.animationsEnabled ? Runtime.Theme.durationNormal : 0 } }
    }
}
