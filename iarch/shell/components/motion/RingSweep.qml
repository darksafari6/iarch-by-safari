// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import "../../runtime" as Runtime

NumberAnimation {
    property int durationMs: Runtime.Theme.durationNormal
    duration: Runtime.Theme.animationsEnabled ? durationMs : 0
    easing.type: Runtime.Theme.easing
}
