// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Minimal shell-core placeholder; full surfaces are supplied by later parts.
// UNTESTED-LIVE: panel geometry and exclusion require a compositor session.
import QtQuick
import Quickshell
import "../runtime" as Runtime
import "../components" as C

PanelWindow {
    id: root
    property string surfaceName: ""
    property var configuration: ({position: "center", variant: "default"})
    property var services: ({})
    property var themeRuntime: null
    property bool preview: false
    readonly property bool vertical: configuration.position === "left" || configuration.position === "right"
    readonly property bool bar: surfaceName === "bar"
    implicitWidth: bar ? (vertical ? 56 : 600) : 360
    implicitHeight: bar ? (vertical ? 600 : 52) : 300
    anchors.top: configuration.position === "top" || (bar && vertical)
    anchors.bottom: configuration.position === "bottom" || (bar && vertical)
    anchors.left: configuration.position === "left" || (bar && !vertical)
    anchors.right: configuration.position === "right" || (bar && !vertical)
    // A preview may overlay a running shell but must not reserve screen space.
    exclusiveZone: !preview && bar ? (vertical ? implicitWidth : implicitHeight) : 0
    color: Runtime.Theme.surface
    SurfaceContent {
        anchors.fill: parent
        surfaceName: root.surfaceName
        vertical: root.vertical
        services: root.services
    }
    C.ThemeTransition { id: transition; anchors.fill: parent; z: 100 }
    Connections {
        target: root.themeRuntime
        function onTransitionRequested(style, previousBackground) { transition.play(style, previousBackground) }
    }
}
