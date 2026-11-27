// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import "../runtime" as Runtime

Item {
    id: root
    property real value: 0
    property string label: ""
    implicitWidth: 100
    implicitHeight: 100
    Accessible.name: label
    Accessible.role: Accessible.ProgressBar
    Canvas {
        id: canvas
        anchors.fill: parent
        onPaint: {
            let ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            let radius = Math.max(0, Math.min(width, height) / 2 - 6)
            let centerX = width / 2, centerY = height / 2
            ctx.lineWidth = 8
            ctx.strokeStyle = Runtime.Theme.outline
            ctx.beginPath(); ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI); ctx.stroke()
            ctx.strokeStyle = Runtime.Theme.accent
            ctx.beginPath(); ctx.arc(centerX, centerY, radius, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * Math.max(0, Math.min(1, root.value))); ctx.stroke()
        }
        Connections { target: root; function onValueChanged() { canvas.requestPaint() } }
        Connections { target: Runtime.Theme; function onAccentChanged() { canvas.requestPaint() } function onOutlineChanged() { canvas.requestPaint() } }
    }
    Text { anchors.centerIn: parent; text: root.label; color: Runtime.Theme.text; font.family: Runtime.Theme.fontUi }
}
