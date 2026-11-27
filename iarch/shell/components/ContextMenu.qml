// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import QtQuick.Controls as Controls
import "../runtime" as Runtime

Controls.Menu {
    id: root
    background: Rectangle { radius: Runtime.Theme.radiusSmall; color: Runtime.Theme.surface; border.color: Runtime.Theme.outline }
}
