// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Stateless quality policy: the preference is never rewritten by an override.
function resolve(preferred, gameMode, lowBattery) {
    let levels = ["low", "balanced", "high", "ultra"]
    let index = levels.indexOf(preferred)
    if (index < 0 || typeof gameMode !== "boolean" || typeof lowBattery !== "boolean") return null
    let effective = gameMode || lowBattery ? "low" : preferred
    let tier = levels.indexOf(effective)
    return {level: effective, blur: tier >= 2, shadows: tier >= 1,
            shaders: tier >= 2, spectrumFps: [10, 24, 40, 60][tier],
            animationScale: [0, 0.75, 1, 1][tier]}
}
if (typeof module !== "undefined" && module.exports) module.exports = {resolve: resolve}
