// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Pure state transitions; this registry does not load compositor windows yet.
var names = ["bar", "overview", "sidebar-right", "sidebar-left", "dock", "osk"]
function configure(layout, previous) {
    if (!layout || typeof layout !== "object" || Array.isArray(layout) || Object.keys(layout).length !== names.length) return null
    let result = {}
    for (let i = 0; i < names.length; ++i) {
        let name = names[i], value = layout[name]
        if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).length !== 5 ||
            !["enabled", "variant", "position", "size", "order"].every(function (k) { return Object.prototype.hasOwnProperty.call(value, k) }) ||
            typeof value.enabled !== "boolean" || typeof value.variant !== "string" || value.variant.length > 120 || !/^[a-z][a-z0-9-]*$/.test(value.variant) ||
            ["top", "bottom", "left", "right", "center"].indexOf(value.position) < 0 ||
            typeof value.size !== "string" || value.size.length > 120 || !/^[a-z][a-z0-9-]*$/.test(value.size) ||
            !Array.isArray(value.order) || !value.order.every(function (x) { return typeof x === "string" && x.length <= 120 && /^[a-z][a-z0-9-]*$/.test(x) }) || new Set(value.order).size !== value.order.length) return null
        result[name] = {available: value.enabled, visible: value.enabled && (previous && previous[name] ? previous[name].visible === true : name === "bar"), variant: value.variant, position: value.position, size: value.size, order: value.order.slice()}
    }
    return result
}
function change(state, name, action) {
    if (!state || !Object.prototype.hasOwnProperty.call(state, name) || !state[name].available ||
        ["open", "close", "toggle"].indexOf(action) < 0) return null
    let copy = JSON.parse(JSON.stringify(state))
    copy[name].visible = action === "toggle" ? !copy[name].visible : action === "open"
    return copy
}
if (typeof module !== "undefined" && module.exports) module.exports = {configure: configure, change: change}
