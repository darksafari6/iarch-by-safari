// Copyright (C) 2026 Safari — GPL-3.0-or-later
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import "../runtime" as Runtime

ListView {
    id: root
    property var items: []
    signal toggled(string itemId, bool done)
    model: items
    clip: true
    implicitWidth: 240
    implicitHeight: 160
    delegate: CheckBox {
        id: check
        required property var modelData
        width: root.width
        text: String(modelData.text || "")
        checked: modelData.done === true
        onToggled: root.toggled(String(modelData.id || ""), checked)
        contentItem: Text { text: check.text; color: Runtime.Theme.text; font.family: Runtime.Theme.fontUi; leftPadding: check.indicator.width + 8; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
    }
}
