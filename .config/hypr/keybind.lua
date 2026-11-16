-- The static half of the keyboard map.
--
-- Every bind this session ships is generated from data/keybinds.default.json into
-- .config/hypr/generated/keybinds.lua by iarch-keybinds, and that file is required
-- before this one (see .config/hypr/hyprland.lua). This file holds the one bind that
-- must not come from the record: the recovery combo. A bind whose job is to repair a
-- broken keyboard map cannot itself live in the file that might be broken, so it is
-- written by hand here and only *described* in the record, under the entry
-- recovery.reapply-defaults with "static": true. iarch-keybinds check proves the two
-- files agree about it, so the description cannot drift from the implementation.
--
-- Do not add any other bind here. A bind the record could hold belongs in the record,
-- because a bind in two places is two handlers on one key and which one runs depends
-- on registration order.
--
-- Why this survives the failures it exists for
-- --------------------------------------------
-- The compositor replaces global `require` with a wrapper that catches a module which
-- loads and then errors: the error goes into the config-error list and an empty table
-- is returned, so the requiring file keeps going
-- (Hyprland v0.57.2 src/config/lua/ConfigManager.cpp:522-527 and :328-360). That is
-- what makes this file reliable: generated/keybinds.lua can fail at runtime, the error
-- is reported, hyprland.lua continues, and this bind still registers.
--
-- The one case it does not cover is the generated file being *missing*, because that
-- path re-raises ("module '...' not found", ConfigManager.cpp:341-346) and aborts
-- hyprland.lua before this file is reached. That case is already handled, and better,
-- by the compositor: with at least one config error and an empty bind registry it trips
-- emergency mode, which registers SUPER + Q for a terminal, SUPER + R for a launcher and
-- SUPER + M to exit (src/config/lua/Emergency.hpp:4-46, recorded in
-- data/design/keybinds.json -> recovery.emergency_mode). So a total failure gets
-- upstream's net and a partial failure gets this one, and neither leaves the session
-- with no way out.
--
-- Both halves of that argument are readings of source, not observations: no compositor
-- was run here. TODO(verify) KB-02 for the require behaviour, KB-01 for this bind
-- firing at all, and KB-05 for whether the emergency launcher hyprland-run is on PATH
-- anywhere, since nothing in this repository installs it.
--
-- The reset runs through os.execute, which blocks, rather than through an async exec.
-- That is deliberate: the bind has to reload the config after the file it just repaired,
-- and an async exec would race the reload and could reload the old map. Upstream's own
-- emergency code uses os.execute the same way (Emergency.hpp:5-10). os and io are
-- available because the compositor opens the full standard library
-- (ConfigManager.cpp:494, luaL_openlibs).

local function iarch_path(env_name, default_suffix)
    -- Mirrors iarch/lib/configstore.py so the recovery combo touches the same file the
    -- CLI and the Settings page do: IARCH_CONFIG_DIR / IARCH_STATE_DIR override, else
    -- XDG-ish defaults under $HOME. configstore also refuses a relative override; here
    -- the bind degrades to the default instead, because a recovery path that raises on
    -- a bad environment variable is worse than one that ignores it.
    local value = os.getenv(env_name)
    if value and value ~= "" and value:sub(1, 1) == "/" then
        return value .. default_suffix
    end
    return (os.getenv("HOME") or "") .. default_suffix
end

local function first_installed_terminal()
    -- The same probe order as the compositor's emergency mode, so a recovery that
    -- cannot run the CLI still leaves the person a shell.
    for _, candidate in ipairs({"kitty", "alacritty", "foot", "wezterm", "gnome-terminal", "xterm"}) do
        if os.execute(("command -v %q >/dev/null 2>&1"):format(candidate)) then
            return candidate
        end
    end
    return nil
end

local function reapply_default_keybinds()
    local override = iarch_path("IARCH_CONFIG_DIR", "/.config/iarch/keybinds.json")
    local terminal = first_installed_terminal()
    local have_cli = os.execute("command -v iarch-keybinds >/dev/null 2>&1")

    -- No CLI means there is nothing this bind can repair, and silently doing nothing
    -- is how a safety net becomes a rumour. Say so on stderr, which the compositor
    -- collects into its config-error report, and open a terminal so the person has a
    -- shell to fix it from -- the same fallback the compositor's own emergency mode
    -- uses.
    if not have_cli then
        io.stderr:write("iarch recovery: iarch-keybinds is not on PATH, so the default "
            .. "map could not be re-applied from this bind. Link it with "
            .. "'<repo>/scripts/iarch-link-cli.sh', which writes ~/.local/bin/"
            .. "iarch-keybinds and says so if that directory is not on PATH; or run "
            .. "'python3 <repo>/iarch/cli/iarch_keybinds.py reset --all --yes' directly.\n")
        if terminal then
            hl.dispatch(hl.dsp.exec_cmd(terminal))
        end
        return
    end

    -- `reset --all` backs the override up, drops it, re-renders the generated file
    -- from the shipped defaults, validates the result and rolls back if it does not
    -- validate -- the rollback is not a flag, because a recovery command whose safety
    -- can be switched off is a trap. Blocking on it is what makes the reload below
    -- safe.
    --
    -- --yes is here because `reset --all` asks first: it discards more than the
    -- person named, so on a terminal it confirms. This bind cannot answer a prompt
    -- and must not try to -- it fires while the session may be broken, and a prompt
    -- on a screen that is not drawing is worse than no prompt. Pressing a dedicated
    -- recovery combination is the explicit intent, and the backup reset keeps is what
    -- makes it reversible rather than merely confirmed.
    os.execute("iarch-keybinds reset --all --yes >/dev/null 2>&1")
    io.stderr:write("iarch recovery: dropped the override at " .. override
        .. " and re-applied the default keyboard map.\n")
    hl.dispatch(hl.dsp.reload_config())
end

hl.bind("CTRL + ALT + R", reapply_default_keybinds)

return true
