// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import "../runtime" as Runtime

Surface {
    id: root
    property string message: ""
    implicitWidth: 280
    implicitHeight: 58
    Accessible.name: message
    Text { anchors.fill: parent; text: root.message; color: Runtime.Theme.text; font.family: Runtime.Theme.fontUi; textFormat: Text.PlainText; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
}
