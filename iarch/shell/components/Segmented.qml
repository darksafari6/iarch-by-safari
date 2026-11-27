// Copyright (C) 2026 Safari — GPL-3.0-or-later
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import "../runtime" as Runtime

Row {
    id: root
    property var options: []
    property int selectedIndex: 0
    signal selected(int index)
    spacing: Runtime.Theme.spacingSmall
    Repeater {
        model: root.options
        Button {
            id: segment
            required property int index
            required property var modelData
            text: String(modelData)
            implicitWidth: 80
            implicitHeight: 36
            Accessible.name: text
            onClicked: { root.selectedIndex = index; root.selected(index) }
            contentItem: Text { text: segment.text; color: segment.index === root.selectedIndex ? Runtime.Theme.accentForeground : Runtime.Theme.text; font.family: Runtime.Theme.fontUi; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
            background: Rectangle { radius: Runtime.Theme.radiusSmall; color: segment.index === root.selectedIndex ? Runtime.Theme.accent : Runtime.Theme.surface; border.color: Runtime.Theme.outline }
        }
    }
}
