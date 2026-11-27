// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Validate the deliberately narrow Python-to-QML projection, not a pack itself.
function exactKeys(object, keys) {
    return object !== null && typeof object === "object" && !Array.isArray(object) &&
        Object.keys(object).length === keys.length && keys.every(function (key) { return Object.prototype.hasOwnProperty.call(object, key) })
}
function whole(value, maximum) {
    return Number.isInteger(value) && value >= 0 && value <= maximum
}
function validate(value) {
    if (!exactKeys(value, ["id", "palette", "radius", "spacing", "fonts", "motion", "shape", "easing", "transition", "surfaceMotion", "variants", "sounds", "surfaceStyle", "quality", "reduceMotion"])) return false
    if (typeof value.id !== "string" || !/^[a-z][a-z0-9]*(-[a-z0-9]+)*$/.test(value.id)) return false
    let colors = ["background", "surface", "text", "accent", "onAccent", "secondary", "error", "outline"]
    if (!exactKeys(value.palette, colors) || !colors.every(function (key) { return typeof value.palette[key] === "string" && /^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(value.palette[key]) })) return false
    if (!exactKeys(value.radius, ["small", "medium", "large"]) || !Object.values(value.radius).every(function (x) { return whole(x, 512) })) return false
    if (!exactKeys(value.spacing, ["small", "medium", "large"]) || !Object.values(value.spacing).every(function (x) { return whole(x, 512) })) return false
    if (!exactKeys(value.fonts, ["ui", "display", "mono"]) || !Object.values(value.fonts).every(function (x) { return typeof x === "string" && x.length > 0 && x.length <= 120 })) return false
    if (!exactKeys(value.motion, ["fast", "normal", "slow"]) || !Object.values(value.motion).every(function (x) { return whole(x, 10000) })) return false
    let tiers = ["none", "xs", "sm", "md", "lg", "xl", "pill"]
    let components = ["window", "panel", "card", "button", "input", "tooltip", "chip", "osk-key"]
    if (!exactKeys(value.shape, ["radius", "components", "chamfer", "border_width", "border_style"]) ||
        !exactKeys(value.shape.radius, tiers) || !tiers.every(function(k) { return whole(value.shape.radius[k], k === "pill" ? 9999 : 512) }) ||
        value.shape.radius.pill < 100 || !exactKeys(value.shape.components, components) ||
        !components.every(function(k) { return tiers.indexOf(value.shape.components[k]) >= 0 }) ||
        !whole(value.shape.chamfer, 512) || !whole(value.shape.border_width, 8) ||
        ["solid", "gradient", "double"].indexOf(value.shape.border_style) < 0) return false
    if (["Linear", "InOutCubic", "OutCubic", "InOutQuad"].indexOf(value.easing) < 0) return false
    if (["none", "fade", "wipe"].indexOf(value.transition) < 0) return false
    let surfaces = ["bar", "overview", "sidebar-right", "sidebar-left", "dock", "osk"]
    if (!exactKeys(value.surfaceMotion, surfaces) || !surfaces.every(function(k) {
        let m = value.surfaceMotion[k]
        return exactKeys(m, ["duration", "style"]) && ["fast", "normal", "slow"].indexOf(m.duration) >= 0 && ["none", "fade", "slide", "scale"].indexOf(m.style) >= 0
    })) return false
    if (!exactKeys(value.variants, surfaces) || !surfaces.every(function(k) {
        return typeof value.variants[k] === "string" && value.variants[k].length <= 120 && /^[a-z][a-z0-9-]*$/.test(value.variants[k])
    })) return false
    let events = ["notification", "volume", "switch"]
    if (!exactKeys(value.sounds, events) || !events.every(function(k) {
        let sound = value.sounds[k]
        return exactKeys(sound, ["enabled", "volume"]) && typeof sound.enabled === "boolean" &&
            typeof sound.volume === "number" && Number.isFinite(sound.volume) && sound.volume >= 0 && sound.volume <= 1
    })) return false
    if (["solid", "glass", "outlined"].indexOf(value.surfaceStyle) < 0) return false
    if (["ultra", "high", "balanced", "low"].indexOf(value.quality) < 0) return false
    return typeof value.reduceMotion === "boolean"
}
if (typeof module !== "undefined" && module.exports) module.exports = { validate: validate }
