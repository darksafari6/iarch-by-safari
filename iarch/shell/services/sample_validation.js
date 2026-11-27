// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Validate local helper responses before making them observable to surfaces.
function object(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value)
}
function integer(value) { return Number.isSafeInteger(value) && value >= 0 }
function usage(value) {
    return value === null || (object(value) && integer(value.total) && integer(value.used) && value.used <= value.total)
}
function stats(value) {
    if (!object(value) || !Object.prototype.hasOwnProperty.call(value, "cpu") ||
        !Object.prototype.hasOwnProperty.call(value, "memory") ||
        !Object.prototype.hasOwnProperty.call(value, "disk") ||
        !Object.prototype.hasOwnProperty.call(value, "temperature") || !object(value.errors)) return false
    if (value.cpu !== null && (!Array.isArray(value.cpu) || value.cpu.length !== 2 ||
        !integer(value.cpu[0]) || !integer(value.cpu[1]) || value.cpu[1] > value.cpu[0])) return false
    if (!usage(value.memory) || !usage(value.disk)) return false
    if (value.temperature !== null && (typeof value.temperature !== "number" ||
        !Number.isFinite(value.temperature) || value.temperature < -50 || value.temperature > 200)) return false
    return Object.keys(value.errors).every(function(key) { return typeof value.errors[key] === "string" })
}
function network(value) {
    if (!object(value) || !Number.isFinite(value.timestamp) || value.timestamp < 0 ||
        !object(value.interfaces) || !Array.isArray(value.networks) ||
        typeof value.available !== "boolean" || (value.error !== null && typeof value.error !== "string")) return false
    let names = Object.keys(value.interfaces)
    if (names.length > 4096 || value.networks.length > 8192) return false
    if (!names.every(function(name) {
        let counters = value.interfaces[name]
        return name.length > 0 && name.length <= 64 && object(counters) && integer(counters.rx) && integer(counters.tx)
    })) return false
    return value.networks.every(function(item) {
        return object(item) && typeof item.active === "boolean" && typeof item.ssid === "string" &&
            item.ssid.length <= 512 && Number.isInteger(item.signal) && item.signal >= 0 && item.signal <= 100
    })
}
if (typeof module !== "undefined" && module.exports) module.exports = {stats: stats, network: network}
