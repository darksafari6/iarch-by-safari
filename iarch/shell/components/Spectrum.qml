// Copyright (C) 2026 Safari — GPL-3.0-or-later
pragma ComponentBehavior: Bound
import QtQuick
import "../runtime" as Runtime

Item {
    id: root
    property var samples: []
    property int barCount: 24
    property int barSpacing: 3
    implicitWidth: 180
    implicitHeight: 50
    Accessible.name: "Audio spectrum"
    Item {
        anchors.fill: parent
        Repeater {
            model: Math.max(0, Math.min(root.barCount, 128))
            Rectangle {
                required property int index
                width: Math.max(0, (root.width - Math.max(0, root.barCount - 1) * root.barSpacing) / Math.max(1, root.barCount))
                x: index * (width + root.barSpacing)
                height: Math.max(2, root.height * Math.max(0, Math.min(1, Number(root.samples[index] || 0))))
                y: root.height - height
                radius: width / 2
                color: Runtime.Theme.accent
            }
        }
    }
}
