// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import "../runtime" as Runtime

AbstractButton {
    id: root
    property string label: ""
    checkable: true
    focusPolicy: Qt.StrongFocus
    implicitWidth: 64
    implicitHeight: 64
    Accessible.name: label
    contentItem: Text { text: root.label; color: root.checked ? Runtime.Theme.accentForeground : Runtime.Theme.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; font.family: Runtime.Theme.fontUi; elide: Text.ElideRight }
    background: Rectangle { radius: width / 2; color: root.checked ? Runtime.Theme.accent : Runtime.Theme.surface; border.width: root.activeFocus ? 2 : 1; border.color: root.activeFocus ? Runtime.Theme.accent : Runtime.Theme.outline }
}
