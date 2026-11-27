// Copyright (C) 2026 Safari — GPL-3.0-or-later
import QtQuick

LocalStore {
    kind: "todo"
    readonly property var items: Array.isArray(data.items) ? data.items : []
    function add(text) { return typeof text === "string" && text.length > 0 && text.length <= 1000 && request({action: "add", text: text}) }
    function toggle(itemId, done) { return typeof itemId === "string" && typeof done === "boolean" && request({action: "toggle", id: itemId, done: done}) }
    function remove(itemId) { return typeof itemId === "string" && request({action: "delete", id: itemId}) }
}
