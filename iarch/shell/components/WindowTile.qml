// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import "../runtime" as Runtime

Button {
    id: root
    property string iconText: ""
    implicitWidth: 220
    implicitHeight: 100
    Accessible.name: text
    contentItem: Text { text: root.iconText + "  " + root.text; textFormat: Text.PlainText; color: Runtime.Theme.text; font.family: Runtime.Theme.fontUi; verticalAlignment: Text.AlignVCenter; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight }
    background: Rectangle { radius: Runtime.Theme.radiusMedium; color: root.down ? Runtime.Theme.outline : Runtime.Theme.surface; border.color: root.activeFocus ? Runtime.Theme.accent : Runtime.Theme.outline; border.width: root.activeFocus ? 2 : 1 }
}
