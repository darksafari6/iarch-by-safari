// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick
import QtQuick.Layouts
import "../runtime" as Runtime

Surface {
    id: root
    property string title: ""
    property string body: ""
    property bool urgent: false
    property string variant: "normal" // normal, urgent, media
    property url coverSource: ""
    signal dismissed()
    signal previousRequested()
    signal toggleRequested()
    signal nextRequested()
    implicitWidth: 320
    implicitHeight: Math.max(110, contentRow.implicitHeight + 32)
    highlighted: urgent || variant === "urgent"
    RowLayout {
        id: contentRow
        anchors.fill: parent
        spacing: Runtime.Theme.spacingMedium
        CoverArt { visible: root.variant === "media"; localSource: root.coverSource; Layout.preferredWidth: 64; Layout.preferredHeight: 64 }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Runtime.Theme.spacingSmall
            Text { text: root.title; textFormat: Text.PlainText; color: root.urgent || root.variant === "urgent" ? Runtime.Theme.error : Runtime.Theme.text; font.family: Runtime.Theme.fontUi; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
            Text { text: root.body; color: Runtime.Theme.text; font.family: Runtime.Theme.fontUi; wrapMode: Text.Wrap; textFormat: Text.PlainText; Layout.fillWidth: true; Layout.fillHeight: true }
            RowLayout {
                visible: root.variant === "media"
                IconButton { iconText: "◀"; Accessible.name: "Previous"; onClicked: root.previousRequested() }
                IconButton { iconText: "▶"; Accessible.name: "Play or pause"; onClicked: root.toggleRequested() }
                IconButton { iconText: "▶▶"; Accessible.name: "Next"; onClicked: root.nextRequested() }
            }
            PillButton { text: "Dismiss"; visible: root.variant !== "media"; onClicked: root.dismissed(); Layout.alignment: Qt.AlignRight }
        }
    }
}
