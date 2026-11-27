// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import "../runtime" as Runtime

Rectangle {
    id: root
    property string text: ""
    property bool active: false
    implicitWidth: label.implicitWidth + 24
    implicitHeight: 30
    radius: height / 2
    color: active ? Runtime.Theme.accent : Runtime.Theme.surface
    border.color: Runtime.Theme.outline
    Text { id: label; anchors.centerIn: parent; text: root.text; color: root.active ? Runtime.Theme.accentForeground : Runtime.Theme.text; font.family: Runtime.Theme.fontUi }
}
