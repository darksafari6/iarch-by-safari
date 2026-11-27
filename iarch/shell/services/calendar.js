// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Calendar model uses local dates and Sunday-first, matching CalendarMonth.
function month(year, month, today) {
    if (!Number.isInteger(year) || year < 100 || year > 9999 || !Number.isInteger(month) || month < 0 || month > 11) return null
    let first = new Date(year, month, 1).getDay()
    let count = new Date(year, month + 1, 0).getDate()
    let result = []
    for (let index = 0; index < 42; ++index) {
        let day = index - first + 1, valid = day >= 1 && day <= count
        result.push({day: valid ? day : 0, inMonth: valid,
                     today: !!today && valid && today.getFullYear() === year && today.getMonth() === month && today.getDate() === day})
    }
    return result
}
if (typeof module !== "undefined" && module.exports) module.exports = {month: month}
