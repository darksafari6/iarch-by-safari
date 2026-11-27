// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Keep notifications in arrival order within groups; never render markup here.
function group(items) {
    if (!Array.isArray(items) || items.length > 200) return []
    let groups = [], indices = new Map()
    for (let item of items) {
        if (!item) continue
        let app = typeof item.appName === "string" && item.appName ? item.appName.slice(0, 200) : ""
        if (!indices.has(app)) { indices.set(app, groups.length); groups.push({app: app, items: []}) }
        groups[indices.get(app)].items.push(item)
    }
    return groups
}
if (typeof module !== "undefined" && module.exports) module.exports = {group: group}
