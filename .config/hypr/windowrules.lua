-- Float rules
hl.window_rule({ match = { class = "^de\\.haeckerfelix\\.Shortwave$" },                   float = true })
hl.window_rule({ match = { class = "^Signal$" },                                          float = true })
hl.window_rule({ match = { class = "^com\\.github\\.rafostar\\.Clapper$" },               float = true })
hl.window_rule({ match = { class = "^app\\.drey\\.Warp$" },                               float = true })
hl.window_rule({ match = { class = "^net\\.davidotek\\.pupgui2$" },                       float = true })
hl.window_rule({ match = { class = "^yad$" },                                             float = true })
hl.window_rule({ match = { class = "^eog$" },                                             float = true })
hl.window_rule({ match = { class = "^io\\.github\\.alainm23\\.planify$" },                float = true })
hl.window_rule({ match = { class = "^io\\.gitlab\\.theevilskeleton\\.Upscaler$" },        float = true })
hl.window_rule({ match = { class = "^com\\.github\\.unrud\\.VideoDownloader$" },          float = true })
hl.window_rule({ match = { class = "^io\\.gitlab\\.adhami3310\\.Impression$" },           float = true })
hl.window_rule({ match = { class = "^io\\.missioncenter\\.MissionCenter$" },              float = true, size = "1290 950"})
hl.window_rule({ match = { class = "^org\\.pulseaudio\\.pavucontrol$" },                  float = true, size = "1221 619", })
hl.window_rule({ match = { title = "^File Operation Progress$" },                         float = true, size = "600 50", })
hl.window_rule({ match = { class = "^xfce-polkit$" },                                     float = true, size = "600 50", })
hl.window_rule({ match = { class = "^[Ss]team$", title = "^.*$" }, float = true })
hl.window_rule({ match = { class = "^steamwebhelper$", title = "^Friends List$" }, float = true })

-- Idle inhibit rules
hl.window_rule({ match = { class = "^(.*celluloid.*|.*mpv.*|.*vlc.*)$" },                                                                                            idle_inhibit = "fullscreen" })
hl.window_rule({ match = { class = "^.*[Ss]potify.*$" },                                                                                                             idle_inhibit = "fullscreen" })
hl.window_rule({ match = { class = "^(.*LibreWolf.*|.*floorp.*|.*brave-browser.*|.*firefox.*|.*chromium.*|.*zen.*|.*vivaldi.*)$" },                                  idle_inhibit = "fullscreen" })

-- Picture-in-picture
hl.window_rule({ match = { title = "^([Pp]icture[-\\s]?[Ii]n[-\\s]?[Pp]icture).*$" }, tag = "picture-in-picture" })
hl.window_rule({ match = { tag = "picture-in-picture" }, float = true, pin = true, keep_aspect_ratio = true, move = "73% 72%", size = "25% 25%" })

-- Opacity rules
--
-- Classes the design system owns are deliberately absent here: tokens.json lists
-- them under app_classes and iarch/cli/gen_glass_lua.py renders their opacity
-- into generated/glass.lua, which is required after this file and so wins.
-- Keeping a pin here too would mean two sources of truth for one window.
--
-- What remains are classes app_classes does not classify. They stay fully
-- opaque by explicit choice -- Electron apps, VMs, capture tools and small
-- dialogues read badly when translucent. Adding one to tokens.app_classes moves
-- it under the generator's control; tests/test_glass_lua.py fails if a pin here
-- contradicts a class the design system owns.
hl.window_rule({ match = { class = "^code-insiders-url-handler$" },                            opacity = 1.0 })
hl.window_rule({ match = { class = "^org\\.kde\\.ark$" },                                      opacity = 1.0 })
hl.window_rule({ match = { class = "^qt5ct$" },                                                opacity = 1.0 })
hl.window_rule({ match = { class = "^qt6ct$" },                                                opacity = 1.0 })
hl.window_rule({ match = { class = "^extsource$" },                                            opacity = 1.0 })
hl.window_rule({ match = { class = "^kvantummanager$" },                                       opacity = 1.0 })
hl.window_rule({ match = { class = "^blueman-manager$" },                                      opacity = 1.0 })
hl.window_rule({ match = { class = "^nm-applet$" },                                            opacity = 1.0 })
hl.window_rule({ match = { class = "^nm-connection-editor$" },                                 opacity = 1.0 })
hl.window_rule({ match = { class = "^org\\.kde\\.polkit-kde-authentication-agent-1$" },        opacity = 1.0 })
hl.window_rule({ match = { class = "^polkit-gnome-authentication-agent-1$" },                  opacity = 1.0 })
hl.window_rule({ match = { class = "^org\\.freedesktop\\.impl\\.portal\\.desktop\\.gtk$" },    opacity = 1.0 })
hl.window_rule({ match = { class = "^org\\.freedesktop\\.impl\\.portal\\.desktop\\.hyprland$" }, opacity = 1.0 })
hl.window_rule({ match = { class = "^[Ss]potify$" },                                           opacity = 1.0 })
hl.window_rule({ match = { initial_title = "^Spotify Free$" },                                 opacity = 1.0 })
hl.window_rule({ match = { initial_title = "^Spotify Premium$" },                              opacity = 1.0 })
hl.window_rule({ match = { class = "^com\\.github\\.tchx84\\.Flatseal$" },                     opacity = 1.0 })
hl.window_rule({ match = { class = "^hu\\.kramo\\.Cartridges$" },                              opacity = 1.0 })
hl.window_rule({ match = { class = "^com\\.obsproject\\.Studio$" },                            opacity = 1.0 })
hl.window_rule({ match = { class = "^gnome-boxes$" },                                          opacity = 1.0 })
hl.window_rule({ match = { class = "^vesktop$" },                                              opacity = 1.0 })
hl.window_rule({ match = { class = "^discord$" },                                              opacity = 1.0 })
hl.window_rule({ match = { class = "^WebCord$" },                                              opacity = 1.0 })
hl.window_rule({ match = { class = "^ArmCord$" },                                              opacity = 1.0 })
hl.window_rule({ match = { class = "^app\\.drey\\.Warp$" },                                    opacity = 1.0 })
hl.window_rule({ match = { class = "^net\\.davidotek\\.pupgui2$" },                            opacity = 1.0 })
hl.window_rule({ match = { class = "^yad$" },                                                  opacity = 1.0 })
hl.window_rule({ match = { class = "^Signal$" },                                               opacity = 1.0 })
hl.window_rule({ match = { class = "^io\\.github\\.alainm23\\.planify$" },                     opacity = 1.0 })
hl.window_rule({ match = { class = "^io\\.gitlab\\.theevilskeleton\\.Upscaler$" },             opacity = 1.0 })
hl.window_rule({ match = { class = "^com\\.github\\.unrud\\.VideoDownloader$" },               opacity = 1.0 })
hl.window_rule({ match = { class = "^io\\.gitlab\\.adhami3310\\.Impression$" },                opacity = 1.0 })
hl.window_rule({ match = { class = "^io\\.github\\.flattool\\.Warehouse$" },                   opacity = 1.0 })
-- Misc rules
hl.window_rule({ match = { class = "^.*jetbrains.*$", title = "^win[0-9]+$" }, no_initial_focus = true })
