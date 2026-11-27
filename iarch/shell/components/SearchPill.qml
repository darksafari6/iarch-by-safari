// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import "../runtime" as Runtime

TextField {
    id: root
    placeholderText: "Type to search"
    implicitWidth: 260
    implicitHeight: 44
    color: Runtime.Theme.text
    placeholderTextColor: Runtime.Theme.secondary
    font.family: Runtime.Theme.fontUi
    leftPadding: 16
    rightPadding: 16
    Accessible.name: placeholderText
    background: Rectangle { radius: height / 2; color: Runtime.Theme.surface; border.width: root.activeFocus ? 2 : 1; border.color: root.activeFocus ? Runtime.Theme.accent : Runtime.Theme.outline }
}
