// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import "../runtime" as Runtime

Rectangle {
    id: root
    property string initials: "?"
    implicitWidth: 48
    implicitHeight: 48
    radius: Math.min(width, height) / 2
    color: Runtime.Theme.surface
    border.color: Runtime.Theme.outline
    Accessible.name: initials
    Text { anchors.centerIn: parent; text: root.initials; color: Runtime.Theme.text; font.family: Runtime.Theme.fontUi; font.bold: true }
}
