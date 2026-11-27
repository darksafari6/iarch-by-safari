// Copyright (C) 2026 Safari — GPL-3.0-or-later
function parse(line, count, maximum) {
    if (typeof line !== "string" || !Number.isInteger(count) || count < 1 || count > 128 || maximum <= 0) return null
    let text = line.trim().replace(/;$/, "")
    if (!text) return null
    let fields = text.split(";")
    if (fields.length !== count) return null
    let result = []
    for (let field of fields) {
        if (!/^[0-9]+$/.test(field)) return null
        let value = Number(field)
        if (!Number.isSafeInteger(value) || value > maximum) return null
        result.push(value / maximum)
    }
    return result
}
if (typeof module !== "undefined" && module.exports) module.exports = {parse: parse}
