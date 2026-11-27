// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import "../runtime" as Runtime

Rectangle {
    id: root
    property string label: ""
    implicitWidth: Math.max(34, caption.implicitWidth + 16)
    implicitHeight: 34
    radius: Runtime.Theme.radiusSmall
    color: Runtime.Theme.surface
    border.color: Runtime.Theme.outline
    Text { id: caption; anchors.centerIn: parent; text: root.label; color: Runtime.Theme.text; font.family: Runtime.Theme.fontUi }
}
