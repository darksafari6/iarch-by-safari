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

-- The values below are the fallback: they hold when no design system has been
-- applied yet. generated/glass.lua, required at the end of this file, sets the
-- same leaves from data/design/tokens.json, and because Hyprland applies window
-- and config values in registration order, whatever is required last wins.
-- It is wrapped in pcall so a session with no generated file still starts.
hl.config({
    general = {
        gaps_in = 2,
        gaps_out = 4,
        border_size = 2,
        resize_on_border = true,
        allow_tearing = false,
        layout = "dwindle",
    },

    decoration = {
        rounding = 8,
        shadow = {
            enabled = true,
        },
        active_opacity = 1.0,
        inactive_opacity = 0.90,
        fullscreen_opacity = 1.0,
        blur = {
            enabled = true,
            size = 1,
            passes = 3,
            new_optimizations = true,
            ignore_opacity = true,
            xray = false,
            special = true,
        },
    },
})

-- Design system: rendered by iarch/cli/gen_glass_lua.py, never edited by hand.
local ok, err = pcall(function()
    require("generated.glass")
end)
if not ok then
    print("[iarch] generated/glass.lua is missing or broken, keeping the static theme: " .. tostring(err))
end
