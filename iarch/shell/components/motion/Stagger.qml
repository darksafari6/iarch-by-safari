// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import "../../runtime" as Runtime

Item {
    id: root
    property bool shown: true
    property int index: 0
    property int stepMs: 35
    property bool revealed: false
    default property alias content: contentItem.data
    function schedule() {
        delay.stop()
        revealed = false
        if (!shown) return
        if (!Runtime.Theme.animationsEnabled || index <= 0) revealed = true
        else delay.restart()
    }
    onShownChanged: schedule()
    Component.onCompleted: schedule()
    Timer { id: delay; interval: Math.max(1, Math.min(10000, root.index * root.stepMs)); onTriggered: root.revealed = root.shown }
    Item {
        id: contentItem
        anchors.fill: parent
        opacity: root.revealed ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Runtime.Theme.animationsEnabled ? Runtime.Theme.durationFast : 0 } }
    }
}
