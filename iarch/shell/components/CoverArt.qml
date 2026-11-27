// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import "../runtime" as Runtime

Rectangle {
    id: root
    // Only a local file may be passed. Never fetch remote album art implicitly.
    property url localSource: ""
    implicitWidth: 120
    implicitHeight: 120
    radius: Runtime.Theme.radiusMedium
    color: Runtime.Theme.surface
    border.color: Runtime.Theme.outline
    clip: true
    gradient: Gradient {
        GradientStop { position: 0; color: Runtime.Theme.surface }
        GradientStop { position: 1; color: Runtime.Theme.outline }
    }
    Image {
        anchors.fill: parent
        source: String(root.localSource).startsWith("file://") ? root.localSource : ""
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        visible: status === Image.Ready
    }
}
