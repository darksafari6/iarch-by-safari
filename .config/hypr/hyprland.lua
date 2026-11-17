local config_home = os.getenv("XDG_CONFIG_HOME")
if not config_home or config_home == "" then
    config_home = (os.getenv("HOME") or "") .. "/.config"
end
local config_dir = config_home .. "/hypr"
package.path = table.concat({
    config_dir .. "/?.lua",
    config_dir .. "/?/init.lua",
    package.path,
}, ";")

-- Clear cached modules so they re-execute on reload (ensures binds/rules re-register)
for _, mod in ipairs({"monitors", "inputs", "generated.keybinds", "keybind", "windowrules", "animations", "generated.animations", "themes.theme", "generated.glass"}) do
    package.loaded[mod] = nil
end

require("monitors")
require("startup")
require("inputs")
-- generated.keybinds is required before keybind so that a render that does not
-- parse leaves the registry empty and the compositor's emergency binds trip; see
-- .config/hypr/keybind.lua and data/design/keybinds.json -> recovery.
require("generated.keybinds")
require("keybind")
require("windowrules")
require("animations")
require("themes.theme")
-- The session theme pack is generated from ~/.config/iarch/theme.json.
-- It is a runtime file under the user's config tree, not a tracked Lua module.
-- loadfile keeps it optional without adding a dangling require() to the load graph.
local theme_chunk, theme_load_error = loadfile(config_dir .. "/generated/theme.lua")
if theme_chunk then
    local theme_ok, theme_err = pcall(theme_chunk)
    if not theme_ok then
        print("[iarch] generated theme failed; keeping the glass fallback: " .. tostring(theme_err))
    end
elseif theme_load_error then
    print("[iarch] generated theme is not present; keeping the glass fallback")
end

hl.config({
    dwindle = {
        preserve_split = true,
    },
    master = {
        new_status = "master",
    },
    misc = {
        vrr = 0,
        disable_hyprland_logo = true,
        disable_splash_rendering = true,
        force_default_wallpaper = 0,
        anr_missed_pings = 5,
        allow_session_lock_restore = true,
    },
    xwayland = {
        force_zero_scaling = true,
    },
    general = {
        snap = {
            enabled = true,
        },
    },
})
