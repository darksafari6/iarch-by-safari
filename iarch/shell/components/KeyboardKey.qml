// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import "../runtime" as Runtime

Button {
    id: root
    implicitWidth: 48
    implicitHeight: 48
    Accessible.name: text
    contentItem: Text { text: root.text; color: Runtime.Theme.text; font.family: Runtime.Theme.fontUi; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
    background: Rectangle { radius: Runtime.Theme.radiusSmall; color: root.down ? Runtime.Theme.outline : Runtime.Theme.surface; border.color: root.activeFocus ? Runtime.Theme.accent : Runtime.Theme.outline; border.width: root.activeFocus ? 2 : 1 }
}
