// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import "../runtime" as Runtime

AbstractButton {
    id: root
    property string label: ""
    property string iconText: ""
    property bool showChevron: false
    checkable: true
    focusPolicy: Qt.StrongFocus
    implicitWidth: 190
    implicitHeight: 58
    Accessible.name: label
    contentItem: Text { leftPadding: 12; rightPadding: 12; text: root.iconText + "  " + root.label + (root.showChevron ? "  ›" : ""); color: root.checked ? Runtime.Theme.accentForeground : Runtime.Theme.text; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; font.family: Runtime.Theme.fontUi }
    background: Rectangle { radius: Runtime.Theme.radiusMedium; color: root.checked ? Runtime.Theme.accent : Runtime.Theme.surface; border.width: root.activeFocus ? 2 : 1; border.color: root.activeFocus ? Runtime.Theme.accent : Runtime.Theme.outline }
}
