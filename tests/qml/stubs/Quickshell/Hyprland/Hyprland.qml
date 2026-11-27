// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Synthetic test double; not a Quickshell implementation.
pragma Singleton
import QtQuick
QtObject { property var focusedMonitor: null; property var focusedWorkspace: null; property var activeToplevel: null; property var monitors: ({values: []}); property var workspaces: ({values: []}); property var toplevels: ({values: []}); signal rawEvent(var event) }
