// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Each enabled visible surface owns its loader; hidden windows are destroyed.
// Placeholder windows do not constitute finished themed surfaces. UNTESTED-LIVE.
import QtQuick
import Quickshell

QtObject {
    id: root
    property var registry: null
    property var themeRuntime: null
    property bool preview: false
    property var services: ({})
    function shown(name) {
        return registry && registry.surfaces[name] && registry.surfaces[name].available && registry.surfaces[name].visible
    }
    function configuration(name) { return registry && registry.surfaces[name] ? registry.surfaces[name] : ({position: "center", variant: "default"}) }
    property var barLoader: LazyLoader {
        activeAsync: !!root.shown("bar")
        SurfaceWindow { surfaceName: "bar"; configuration: root.configuration("bar"); services: root.services; preview: root.preview; themeRuntime: root.themeRuntime }
    }
    property var overviewLoader: LazyLoader {
        activeAsync: !!root.shown("overview")
        SurfaceWindow { surfaceName: "overview"; configuration: root.configuration("overview"); services: root.services; preview: root.preview; themeRuntime: root.themeRuntime }
    }
    property var sidebar_rightLoader: LazyLoader {
        activeAsync: !!root.shown("sidebar-right")
        SurfaceWindow { surfaceName: "sidebar-right"; configuration: root.configuration("sidebar-right"); services: root.services; preview: root.preview; themeRuntime: root.themeRuntime }
    }
    property var sidebar_leftLoader: LazyLoader {
        activeAsync: !!root.shown("sidebar-left")
        SurfaceWindow { surfaceName: "sidebar-left"; configuration: root.configuration("sidebar-left"); services: root.services; preview: root.preview; themeRuntime: root.themeRuntime }
    }
    property var dockLoader: LazyLoader {
        activeAsync: !!root.shown("dock")
        SurfaceWindow { surfaceName: "dock"; configuration: root.configuration("dock"); services: root.services; preview: root.preview; themeRuntime: root.themeRuntime }
    }
    property var oskLoader: LazyLoader {
        activeAsync: !!root.shown("osk")
        SurfaceWindow { surfaceName: "osk"; configuration: root.configuration("osk"); services: root.services; preview: root.preview; themeRuntime: root.themeRuntime }
    }
}
