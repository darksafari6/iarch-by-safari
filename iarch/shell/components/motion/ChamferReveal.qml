// Copyright (C) 2026 Safari — GPL-3.0-or-later
// A masked, angled reveal. No shader or animation in low/reduced-motion mode.
// UNTESTED-LIVE: mask rendering and pointer delivery need a Qt session.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Effects
import "../../runtime" as Runtime

Item {
    id: root
    property bool shown: true
    property real chamfer: Runtime.Theme.chamfer
    property real progress: shown ? 1 : 0
    readonly property bool useMask: Runtime.Theme.shadersEnabled && Runtime.Theme.animationsEnabled
    default property alias content: contentItem.data
    Behavior on progress { NumberAnimation { duration: Runtime.Theme.animationsEnabled ? Runtime.Theme.durationNormal : 0; easing.type: Runtime.Theme.easing } }
    onProgressChanged: mask.requestPaint()
    onChamferChanged: mask.requestPaint()
    Item {
        id: contentItem
        anchors.fill: parent
        visible: root.shown || root.progress > 0
        opacity: root.useMask ? 1 : (root.shown ? 1 : 0)
        layer.enabled: root.useMask
        layer.effect: MultiEffect { maskEnabled: true; maskSource: mask }
    }
    Canvas {
        id: mask
        anchors.fill: parent
        visible: false
        layer.enabled: true
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            let ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            let p = Math.max(0, Math.min(1, root.progress))
            let cut = Math.max(0, Math.min(root.chamfer, height / 2, width / 2))
            let right = width * p
            if (right <= 0) return
            let angle = Math.min(cut, right / 2)
            ctx.fillStyle = Runtime.Theme.text
            ctx.beginPath()
            ctx.moveTo(angle, 0)
            ctx.lineTo(right, 0)
            ctx.lineTo(right, height - angle)
            ctx.lineTo(right - angle, height)
            ctx.lineTo(0, height)
            ctx.lineTo(0, angle)
            ctx.closePath()
            ctx.fill()
        }
    }
}
