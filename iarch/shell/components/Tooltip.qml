// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import QtQuick.Controls as Controls
import "../runtime" as Runtime

Controls.ToolTip {
    id: root
    delay: 500
    contentItem: Text { text: root.text; color: Runtime.Theme.text; font.family: Runtime.Theme.fontUi }
    background: Rectangle { radius: Runtime.Theme.radiusSmall; color: Runtime.Theme.surface; border.color: Runtime.Theme.outline }
}
