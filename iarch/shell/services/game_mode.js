// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Extract the existing settings record without changing other settings.
function parse(text) {
    try {
        let value = JSON.parse(text)
        if (!value || typeof value !== "object" || Array.isArray(value)) return null
        if (value.modes === undefined) return false
        if (!value.modes || typeof value.modes !== "object" || Array.isArray(value.modes)) return null
        if (value.modes.game === undefined) return false
        if (!value.modes.game || typeof value.modes.game !== "object" || Array.isArray(value.modes.game)) return null
        if (value.modes.game.active === undefined) return false
        return typeof value.modes.game.active === "boolean" ? value.modes.game.active : null
    } catch (e) { return null }
}
// Match the existing animation preference; absent fields use the recorded
// default, while malformed records never replace the last valid state.
function reduceMotion(text) {
    try {
        let value = JSON.parse(text)
        if (!value || typeof value !== "object" || Array.isArray(value)) return null
        if (value.animation === undefined) return false
        if (!value.animation || typeof value.animation !== "object" || Array.isArray(value.animation)) return null
        if (value.animation.reduce_motion === undefined) return false
        return typeof value.animation.reduce_motion === "boolean" ? value.animation.reduce_motion : null
    } catch (e) { return null }
}
if (typeof module !== "undefined" && module.exports) module.exports = {parse: parse, reduceMotion: reduceMotion}
