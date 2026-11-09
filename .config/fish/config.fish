# Settings below apply only to interactive terminals, not scripts or SSH commands.
if status is-interactive
    set -g fish_greeting "Welcome to minimaLinux · Super+D opens the launcher"

    # Fish provides autosuggestions and syntax highlighting out of the box.
    # Right arrow accepts a suggestion; Ctrl+Right accepts the next word.
    set -g fish_autosuggestion_enabled 1
    set -g fish_color_autosuggestion 7a88b5
    set -g fish_color_command 7aa2f7
    set -g fish_color_param c0caf5
    set -g fish_color_error f7768e
    set -g fish_color_quote 9ece6a

    if command -q fastfetch
        fastfetch
    end
    if command -q starship
        function starship_transient_prompt_func
            starship module character
        end
        function starship_transient_rprompt_func
            starship module custom.transient_time
        end
        starship init fish | source
    end
    if command -q zoxide
        zoxide init fish | source
    end
    if not set -q FZF_DEFAULT_OPTS
        set -gx FZF_DEFAULT_OPTS '--color=bg+:#292e42,bg:#1a1b26,fg:#c0caf5,fg+:#c0caf5,hl:#7aa2f7,hl+:#7aa2f7,info:#7dcfff,prompt:#bb9af7,pointer:#bb9af7,marker:#9ece6a'
    end
    if command -q fzf
        # Adds Ctrl+R history search, Ctrl+T file search, and Alt+C directory search.
        fzf --fish | source
    end
    if command -q eza
        alias ll 'eza -lah --icons=auto'
        alias lt 'eza --tree --level=2 --icons=auto'
    else
        alias ll 'ls -lah'
    end
end
