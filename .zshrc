# Pywal colors
(cat ~/.cache/wal/sequences &)

# Fastfetch on interactive shell
if [[ $- == *i* ]]; then
	fastfetch
fi

# Powerlevel10k instant prompt (must stay near the top)
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

# ---------- Oh My Zsh ----------
export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="powerlevel10k/powerlevel10k"

plugins=(
	git
	zoxide
	sudo
	fzf
	extract
)

source $ZSH/oh-my-zsh.sh

# ---------- History ----------
HISTSIZE=50000
SAVEHIST=50000
setopt HIST_IGNORE_ALL_DUPS
setopt HIST_SAVE_NO_DUPS
setopt HIST_REDUCE_BLANKS
setopt SHARE_HISTORY
setopt INC_APPEND_HISTORY

# ---------- Environment ----------
export MANPAGER='nvim +Man!'
export PATH="$HOME/.local/bin:$HOME/.local/share/flatpak/exports/bin:$PATH"

# pnpm
export PNPM_HOME="$HOME/.local/share/pnpm"
case ":$PATH:" in
  *":$PNPM_HOME:"*) ;;
  *) export PATH="$PNPM_HOME:$PATH" ;;
esac

# bun
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"
[ -s "$BUN_INSTALL/_bun" ] && source "$BUN_INSTALL/_bun"

# ---------- Aliases ----------
alias v='nvim'
alias cd='z'
alias szrc='source ~/.zshrc'
alias zrc='v ~/.zshrc'
alias swrc='v ~/.config/sway/config'
alias kitc='v ~/.config/kitty/kitty.conf'
alias ..='cd ..'
alias ...='cd ../..'
alias cp='cp -i'
alias mv='mv -i'
alias grep='grep --color=auto'
alias c='clear'
alias ls='eza -a --icons'
alias lt='eza --tree --level=2 --icons'
alias lg='lazygit'

# ---------- Functions ----------
chpwd() { ls }
mkcd() { mkdir -p "$1" && cd "$1" }

# ---------- Sources ----------
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh
[ -f ~/fzfrc ] && source ~/fzfrc

# opencode
export PATH="$HOME/.opencode/bin:$PATH"
