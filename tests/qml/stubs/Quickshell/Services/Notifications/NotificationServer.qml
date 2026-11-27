// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Synthetic test double; not a Quickshell implementation.
import QtQuick
QtObject { property bool bodyMarkupSupported; property bool bodyHyperlinksSupported; property bool persistenceSupported; property bool actionsSupported; property bool imageSupported; property var trackedNotifications: ({values: []}); signal notification(var notification) }
