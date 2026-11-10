require("animations.default")

-- Design system: rendered by iarch/cli/gen_animations_lua.py, never edited by hand.
-- Required after the static default so the token-driven curves and leaf speeds win;
-- wrapped in pcall so a session with no generated file still animates.
local ok, err = pcall(function()
    require("generated.animations")
end)
if not ok then
    print("[iarch] generated/animations.lua is missing or broken, keeping the static animations: " .. tostring(err))
end
