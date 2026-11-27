// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Parse only the documented main keyboard state, never execute device names.
function parse(text) {
    if (typeof text !== "string" || text.length > 1048576) return null
    let data
    try { data = JSON.parse(text) } catch (_) { return null }
    if (!data || !Array.isArray(data.keyboards) || data.keyboards.length > 256) return null
    let main = data.keyboards.filter(function(k) { return k && k.main === true })
    if (main.length !== 1) return null
    let keyboard = main[0]
    if (typeof keyboard.name !== "string" || keyboard.name.length > 512 ||
        typeof keyboard.active_keymap !== "string" || keyboard.active_keymap.length > 512) return null
    return {name: keyboard.name, layout: keyboard.active_keymap,
            capsLock: keyboard.capsLock === true, numLock: keyboard.numLock === true}
}
if (typeof module !== "undefined" && module.exports) module.exports = {parse: parse}
