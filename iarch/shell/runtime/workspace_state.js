// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Pure indicator/navigation state; requests must be sent by a compositor adapter.
function validWorkspace(value) { return Number.isInteger(value) && value >= 1 && value <= 10 }
function step(current, delta) {
    if (!validWorkspace(current) || !Number.isInteger(delta) || Math.abs(delta) > 1000) return null
    return ((current - 1 + (delta % 10) + 10) % 10) + 1
}
function select(current, direction) {
    if (!validWorkspace(current)) return null
    let index = current - 1, row = Math.floor(index / 5), col = index % 5
    if (direction === "left") col = Math.max(0, col - 1)
    else if (direction === "right") col = Math.min(4, col + 1)
    else if (direction === "up") row = Math.max(0, row - 1)
    else if (direction === "down") row = Math.min(1, row + 1)
    else return null
    return row * 5 + col + 1
}
function indicator(current, occupied) {
    if (!validWorkspace(current) || !Array.isArray(occupied) || !occupied.every(validWorkspace)) return null
    let set = new Set(occupied), result = []
    for (let n = 1; n <= 10; ++n) result.push({id: n, active: n === current, occupied: set.has(n)})
    return result
}
if (typeof module !== "undefined" && module.exports) module.exports = {step: step, select: select, indicator: indicator}
