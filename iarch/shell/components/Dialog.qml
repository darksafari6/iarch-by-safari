// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import QtQuick.Controls as Controls
import "../runtime" as Runtime

Controls.Dialog {
    id: root
    modal: true
    focus: true
    closePolicy: Controls.Popup.CloseOnEscape
    background: Rectangle { radius: Runtime.Theme.radiusLarge; color: Runtime.Theme.surface; border.color: Runtime.Theme.outline; border.width: 1 }
}
