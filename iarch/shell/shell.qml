// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Reserved entry point. A runnable shell is delivered at milestone M1.
import QtQuick
import Quickshell
import "runtime" as Runtime

ShellRoot {
    property var themeRuntime: Runtime.ThemeRuntime {}
    property var surfaceRegistry: Runtime.SurfaceRegistry {}
}
