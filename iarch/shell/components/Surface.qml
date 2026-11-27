// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Pure theme-token surface. Canvas rendering is UNTESTED-LIVE.
import QtQuick
import "../runtime" as Runtime

Item {
    id: root
    property string surfaceStyle: Runtime.Theme.tokens.surfaceStyle
    property bool highlighted: false
    property alias content: contentItem.data
    default property alias childrenData: contentItem.data
    implicitWidth: 240
    implicitHeight: 120
    opacity: surfaceStyle === "glass" && Runtime.Theme.quality !== "low" ? 0.9 : 1.0
    onSurfaceStyleChanged: canvas.requestPaint()
    onHighlightedChanged: canvas.requestPaint()
    Canvas {
        id: canvas
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections {
            target: Runtime.Theme
            function onTokensChanged() { canvas.requestPaint() }
            function onSurfaceChanged() { canvas.requestPaint() }
            function onAccentChanged() { canvas.requestPaint() }
            function onOutlineChanged() { canvas.requestPaint() }
        }
        onPaint: {
            let ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            if (width <= 0 || height <= 0) return
            function outline(inset) {
                let w = width - inset * 2, h = height - inset * 2
                if (w <= 0 || h <= 0) return false
                let x = inset, y = inset
                let cut = Math.max(0, Math.min(Runtime.Theme.chamfer, w / 2, h / 2))
                let radius = Math.max(0, Math.min(Runtime.Theme.radiusLarge, w / 2, h / 2))
                ctx.beginPath()
                if (cut > 0) {
                    ctx.moveTo(x + cut, y); ctx.lineTo(x + w - cut, y); ctx.lineTo(x + w, y + cut)
                    ctx.lineTo(x + w, y + h - cut); ctx.lineTo(x + w - cut, y + h)
                    ctx.lineTo(x + cut, y + h); ctx.lineTo(x, y + h - cut); ctx.lineTo(x, y + cut)
                } else {
                    ctx.moveTo(x + radius, y); ctx.lineTo(x + w - radius, y)
                    ctx.quadraticCurveTo(x + w, y, x + w, y + radius)
                    ctx.lineTo(x + w, y + h - radius); ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h)
                    ctx.lineTo(x + radius, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - radius)
                    ctx.lineTo(x, y + radius); ctx.quadraticCurveTo(x, y, x + radius, y)
                }
                ctx.closePath()
                return true
            }
            let stroke = Math.max(0, Math.min(Runtime.Theme.borderWidth, Math.min(width, height) / 2))
            if (outline(stroke / 2)) {
                if (root.surfaceStyle !== "outlined") { ctx.fillStyle = Runtime.Theme.surface; ctx.fill() }
                if (stroke > 0) {
                    ctx.lineWidth = stroke
                    if (Runtime.Theme.borderStyle === "gradient") {
                        let gradient = ctx.createLinearGradient(0, 0, width, height)
                        gradient.addColorStop(0, Runtime.Theme.accent)
                        gradient.addColorStop(1, Runtime.Theme.outline)
                        ctx.strokeStyle = gradient
                    } else ctx.strokeStyle = root.highlighted ? Runtime.Theme.accent : Runtime.Theme.outline
                    ctx.stroke()
                }
            }
            if (stroke > 0 && Runtime.Theme.borderStyle === "double" && outline(stroke * 2.5)) {
                ctx.lineWidth = stroke
                ctx.strokeStyle = root.highlighted ? Runtime.Theme.accent : Runtime.Theme.outline
                ctx.stroke()
            }
        }
    }
    Item { id: contentItem; anchors.fill: parent; anchors.margins: Runtime.Theme.spacingLarge }
}
