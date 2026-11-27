// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import QtQuick.Controls as Controls
import "../runtime" as Runtime

Controls.Slider {
    id: root
    implicitWidth: 180
    implicitHeight: 32
    focusPolicy: Qt.StrongFocus
    background: Rectangle {
        x: root.leftPadding; y: root.topPadding + root.availableHeight / 2 - height / 2
        width: root.availableWidth; height: 6; radius: height / 2; color: Runtime.Theme.outline
        Rectangle { width: root.visualPosition * parent.width; height: parent.height; radius: height / 2; color: Runtime.Theme.accent }
    }
    handle: Rectangle {
        x: root.leftPadding + root.visualPosition * (root.availableWidth - width)
        y: root.topPadding + root.availableHeight / 2 - height / 2
        width: 20; height: 20; radius: 10; color: Runtime.Theme.accent
        border.width: root.activeFocus ? 2 : 0; border.color: Runtime.Theme.text
    }
}
