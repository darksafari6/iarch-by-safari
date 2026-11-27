// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import QtQuick.Controls as Controls
import "../runtime" as Runtime

Controls.TextField {
    id: root
    implicitWidth: 220
    implicitHeight: 40
    color: Runtime.Theme.text
    placeholderTextColor: Runtime.Theme.secondary
    font.family: Runtime.Theme.fontUi
    leftPadding: 12
    rightPadding: 12
    background: Rectangle { radius: Runtime.Theme.radiusSmall; color: Runtime.Theme.surface; border.width: root.activeFocus ? 2 : 1; border.color: root.activeFocus ? Runtime.Theme.accent : Runtime.Theme.outline }
}
