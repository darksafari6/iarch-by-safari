// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Standalone QtQuick gallery; the host supplies validated theme choices.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import "components" as C
import "runtime" as Runtime

Window {
    id: root
    title: "iArch by Safari — Component Gallery"
    width: 1000; height: 760
    minimumWidth: 600; minimumHeight: 400
    color: Runtime.Theme.background
    property var transitionRuntime: null
    property var themes: []
    property string error: ""
    signal themeRequested(string themeId)

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        Column {
            width: parent.width
            padding: 20
            spacing: Runtime.Theme.spacingLarge
            Text { text: "Component Gallery"; color: Runtime.Theme.text; font.pixelSize: 26; font.family: Runtime.Theme.fontUi }
            Row {
                spacing: Runtime.Theme.spacingMedium
                Text { text: "Theme"; color: Runtime.Theme.text; anchors.verticalCenter: parent.verticalCenter }
                ComboBox {
                    id: themePicker
                    model: root.themes
                    enabled: count > 0
                    onActivated: root.themeRequested(String(currentText))
                }
                Text { text: "Current: " + Runtime.Theme.tokens.id; color: Runtime.Theme.text; anchors.verticalCenter: parent.verticalCenter }
            }
            Text { text: root.error; color: Runtime.Theme.error; visible: root.error.length > 0; wrapMode: Text.Wrap; width: parent.width - 40 }
            Flow {
                width: parent.width - 40
                spacing: Runtime.Theme.spacingLarge
                C.Surface { implicitWidth: 210; implicitHeight: 90; surfaceStyle: "solid"; Text { anchors.centerIn: parent; text: "Solid"; color: Runtime.Theme.text } }
                C.Surface { implicitWidth: 210; implicitHeight: 90; surfaceStyle: "glass"; Text { anchors.centerIn: parent; text: "Glass"; color: Runtime.Theme.text } }
                C.Surface { implicitWidth: 210; implicitHeight: 90; surfaceStyle: "outlined"; highlighted: true; Text { anchors.centerIn: parent; text: "Outlined"; color: Runtime.Theme.text } }
                C.Card { implicitWidth: 210; implicitHeight: 90; Text { anchors.centerIn: parent; text: "Card"; color: Runtime.Theme.text } }
                C.Chip { text: "Chip" }
                C.Chip { text: "Active"; active: true }
                C.PillButton { text: "Button" }
                C.PillButton { text: "Disabled"; enabled: false }
                C.IconButton { iconText: "+"; Accessible.name: "Add" }
                C.RoundIconButton { iconText: "×"; Accessible.name: "Close" }
                C.ToggleTile { label: "Inactive"; iconText: "○"; showChevron: true }
                C.ToggleTile { label: "Active"; iconText: "●"; checked: true }
                C.ToggleCircle { label: "Off" }
                C.ToggleCircle { label: "On"; checked: true }
                C.Slider { value: 0.6 }
                C.ProgressBar { value: 0.65 }
                C.RingGauge { value: 0.72; label: "72%" }
                C.Segmented { options: ["One", "Two", "Three"]; selectedIndex: 1 }
                C.Tabs { options: ["Overview", "Details"] }
                C.TextField { placeholderText: "Text field" }
                C.SearchPill { }
                C.Avatar { initials: "IS" }
                C.CoverArt { }
                C.Spectrum { samples: [0.1, 0.25, 0.5, 0.8, 0.4, 0.2, 0.3]; barCount: 7 }
                C.Keycap { label: "Ctrl" }
                C.KeyboardKey { text: "A" }
                C.CalendarMonth { }
                C.TodoList { items: [{id: "one", text: "Example task", done: false}, {id: "two", text: "Completed task", done: true}] }
                C.NotificationCard { title: "Notification"; body: "A regular notification" }
                C.NotificationCard { title: "Urgent"; body: "An urgent notification"; variant: "urgent" }
                C.NotificationCard { title: "Track title"; body: "Artist"; variant: "media" }
                C.WorkspaceDots { count: 5; current: 1; shape: "dots" }
                C.WorkspaceDots { count: 5; current: 2; shape: "bubbles" }
                C.WorkspaceDots { count: 5; current: 3; shape: "pill" }
                C.WorkspaceIndicator { current: 2; occupied: [1, 2, 4]; style: "pill-group" }
                C.WindowTile { text: "Window"; iconText: "□" }
                C.Toast { message: "Saved successfully" }
                C.Icon { name: "wifi"; glyph: "★" }
                C.PillButton { text: "Menu"; onClicked: menu.open() }
                C.PillButton { text: "Dialog"; onClicked: dialog.open() }
                C.PillButton { text: "Tooltip"; onHoveredChanged: tip.visible = hovered }
            }
        }
    }
    C.ThemeTransition { id: transition; anchors.fill: parent; z: 100 }
    Connections { target: root.transitionRuntime; function onTransitionRequested(style, previousBackground) { transition.play(style, previousBackground) } }
    C.ContextMenu { id: menu; MenuItem { text: "Example" } }
    C.Dialog { id: dialog; title: "Example dialog"; standardButtons: Dialog.Ok | Dialog.Cancel }
    C.Tooltip { id: tip; text: "Example tooltip" }
}
