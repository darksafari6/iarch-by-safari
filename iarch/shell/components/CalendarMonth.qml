// Copyright (C) 2026 Safari — GPL-3.0-or-later
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import "../runtime" as Runtime

Column {
    id: root
    property int year: new Date().getFullYear()
    property int month: new Date().getMonth() // zero-based, as in JavaScript Date
    property int selectedDay: 0
    signal daySelected(int day)
    readonly property int firstWeekday: new Date(year, month, 1).getDay()
    readonly property int daysInMonth: new Date(year, month + 1, 0).getDate()
    spacing: Runtime.Theme.spacingSmall
    Accessible.name: "Calendar month"
    Text { text: Qt.formatDate(new Date(root.year, root.month, 1), "MMMM yyyy"); color: Runtime.Theme.text; font.family: Runtime.Theme.fontUi }
    Grid {
        columns: 7
        spacing: Runtime.Theme.spacingSmall
        Repeater {
            model: 42
            Button {
                id: dayButton
                required property int index
                readonly property int day: index - root.firstWeekday + 1
                readonly property bool validDay: day > 0 && day <= root.daysInMonth
                enabled: validDay
                opacity: validDay ? 1 : 0
                text: validDay ? String(day) : ""
                implicitWidth: 32; implicitHeight: 32
                Accessible.name: text
                onClicked: { root.selectedDay = day; root.daySelected(day) }
                contentItem: Text { text: dayButton.text; color: dayButton.day === root.selectedDay ? Runtime.Theme.accentForeground : Runtime.Theme.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; font.family: Runtime.Theme.fontUi }
                background: Rectangle { radius: Runtime.Theme.radiusSmall; color: dayButton.day === root.selectedDay ? Runtime.Theme.accent : Runtime.Theme.surface }
            }
        }
    }
}
