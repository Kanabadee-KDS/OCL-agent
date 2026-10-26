#!/bin/sh
# Open (or reattach to) the OCL Agent tmux session: project name at the top of the
# window and in the terminal title, current commit on the right.
# Options are set on this session only (never ~/.tmux.conf), because the arsoft
# account is shared with HRIS and hr_recruit, whose tmux sessions keep their own look.
set -e
S=ocl
NAME="OCL Agent"
cd "$(dirname "$0")/.."
REPO=$(pwd)

if ! tmux has-session -t "$S" 2>/dev/null; then
  tmux new-session -d -s "$S" -n "$NAME" -c "$REPO"
  tmux set-option -t "$S" status-position top
  tmux set-option -t "$S" status-style "bg=colour24,fg=white"
  tmux set-option -t "$S" status-left-length 20
  tmux set-option -t "$S" status-left "#[bold] $NAME #[nobold]| "
  tmux set-option -t "$S" status-right-length 40
  tmux set-option -t "$S" status-right " #(git -C '$REPO' rev-parse --short HEAD) | %H:%M "
  tmux set-option -t "$S" set-titles on
  tmux set-option -t "$S" set-titles-string "$NAME - #W"
  tmux set-window-option -t "$S" automatic-rename off
fi

if [ -n "$TMUX" ]; then
  exec tmux switch-client -t "$S"
fi
exec tmux attach-session -t "$S"
