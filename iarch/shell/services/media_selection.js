// Copyright (C) 2026 Safari — GPL-3.0-or-later
function choose(list, preferred) {
    let ordered = Array.from(list).filter(function(p) { return p !== null })
    ordered.sort(function(a, b) { return a.dbusName < b.dbusName ? -1 : a.dbusName > b.dbusName ? 1 : 0 })
    let selected = preferred ? ordered.find(function(p) { return p.dbusName === preferred }) : null
    return selected || ordered.find(function(p) { return p.isPlaying }) || ordered[0] || null
}
if (typeof module !== "undefined" && module.exports) module.exports = {choose: choose}
