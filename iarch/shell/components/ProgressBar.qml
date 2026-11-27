// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import QtQuick.Controls as Controls
import "../runtime" as Runtime

Controls.ProgressBar {
    id: root
    implicitWidth: 180
    implicitHeight: 8
    background: Rectangle { radius: height / 2; color: Runtime.Theme.surface; border.color: Runtime.Theme.outline }
    contentItem: Item { Rectangle { width: parent.width * root.visualPosition; height: parent.height; radius: height / 2; color: Runtime.Theme.accent } }
}
