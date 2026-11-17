local env = {
    "HYPRCURSOR_THEME,Bibata-Modern-Classic",
    "HYPRCURSOR_SIZE,24",
    "XCURSOR_THEME,Bibata-Modern-Classic",
    "XCURSOR_SIZE,24",
    "QT_CURSOR_THEME,Bibata-Modern-Classic",
    "QT_CURSOR_SIZE,24",
}

for _, item in ipairs(env) do
    local key, value = item:match("^([^,]+),(.+)$")
    if key and value then
        hl.env(key, value)
    end
end

-- This file exports cursor settings only. Session appearance is loaded from
-- generated/glass.lua as a compatibility fallback, then generated/theme.lua
-- (the selected data/themes/<id>.json pack) by hyprland.lua. Keep values out
-- of this source file so there is only one per-theme definition.

-- Design system: rendered by iarch/cli/gen_glass_lua.py, never edited by hand.
local ok, err = pcall(function()
    require("generated.glass")
end)
if not ok then
    print("[iarch] generated/glass.lua is missing or broken, keeping the glass fallback: " .. tostring(err))
end
