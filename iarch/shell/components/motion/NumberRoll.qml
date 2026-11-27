// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import "../../runtime" as Runtime

Text {
    id: root
    property real value: 0
    property int decimals: 0
    property real displayedValue: value
    text: displayedValue.toFixed(Math.max(0, Math.min(10, decimals)))
    color: Runtime.Theme.text
    font.family: Runtime.Theme.fontUi
    Behavior on displayedValue { NumberAnimation { duration: Runtime.Theme.animationsEnabled ? Runtime.Theme.durationNormal : 0; easing.type: Runtime.Theme.easing } }
}
