// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import "../runtime" as Runtime

Button {
    id: root
    implicitWidth: Math.max(96, label.implicitWidth + 32)
    implicitHeight: 40
    focusPolicy: Qt.StrongFocus
    Accessible.name: text
    contentItem: Text {
        id: label
        text: root.text
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        color: root.enabled ? Runtime.Theme.text : Runtime.Theme.outline
        font.family: Runtime.Theme.fontUi
    }
    background: Rectangle {
        radius: height / 2
        color: root.down ? Runtime.Theme.outline : Runtime.Theme.surface
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? Runtime.Theme.accent : Runtime.Theme.outline
    }
}
