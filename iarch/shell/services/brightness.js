// Copyright (C) 2026 Safari — GPL-3.0-or-later
function parse(text) {
    let fields = text.trim().split(",")
    if (fields.length !== 5 || !fields[0] || fields[1] !== "backlight" ||
        !/^[0-9]+$/.test(fields[2]) || !/^[0-9]+%$/.test(fields[3]) || !/^[0-9]+$/.test(fields[4])) return null
    let current = Number(fields[2]), maximum = Number(fields[4]), percent = Number(fields[3].slice(0, -1))
    if (!Number.isSafeInteger(current) || !Number.isSafeInteger(maximum) || maximum <= 0 || current > maximum || percent > 100) return null
    return {device: fields[0], current: current, maximum: maximum, percent: percent}
}
if (typeof module !== "undefined" && module.exports) module.exports = {parse: parse}
