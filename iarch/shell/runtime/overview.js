// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Pure layout calculations for the overview; no compositor dependencies.
function finite(value) { return typeof value === "number" && Number.isFinite(value) }

// The workspace grid is always 5 by 2, with nonnegative cells even on tiny displays.
function grid(width, height, gap) {
    if (![width, height, gap].every(finite) || width < 0 || height < 0 || gap < 0) return null
    let gx = Math.min(gap, width / 4), gy = Math.min(gap, height)
    let w = Math.max(0, (width - gx * 4) / 5), h = Math.max(0, (height - gy) / 2)
    let cells = []
    for (let i = 0; i < 10; ++i) cells.push({workspace: i + 1, x: (i % 5) * (w + gx), y: Math.floor(i / 5) * (h + gy), width: w, height: h})
    return cells
}

// Map compositor monitor coordinates into a workspace tile using a uniform scale.
// Clipping keeps offscreen windows inside the monitor and tile bounds.
function windowRect(monitor, window, tile) {
    if (!monitor || !window || !tile) return null
    for (let rect of [monitor, window, tile]) {
        if (![rect.x, rect.y, rect.width, rect.height].every(finite) || rect.width <= 0 || rect.height <= 0) return null
    }
    let left = Math.max(monitor.x, window.x), top = Math.max(monitor.y, window.y)
    let right = Math.min(monitor.x + monitor.width, window.x + window.width)
    let bottom = Math.min(monitor.y + monitor.height, window.y + window.height)
    if (right <= left || bottom <= top) return null
    let scale = Math.min(tile.width / monitor.width, tile.height / monitor.height)
    let ox = tile.x + (tile.width - monitor.width * scale) / 2
    let oy = tile.y + (tile.height - monitor.height * scale) / 2
    return {x: ox + (left - monitor.x) * scale, y: oy + (top - monitor.y) * scale,
            width: (right - left) * scale, height: (bottom - top) * scale}
}
if (typeof module !== "undefined" && module.exports) module.exports = {grid: grid, windowRect: windowRect}
