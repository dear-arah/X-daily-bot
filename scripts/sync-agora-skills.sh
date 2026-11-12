#!/bin/sh
# Usage: sync-agora-skills.sh DIR
# Fetches the current Agora skills knowledge pack (public, MIT) into DIR.
# A failed clone only warns: a missing pack must not stop the bot.
dir="${1:?target directory}"
rm -rf "$dir"
if git clone --quiet --depth 1 https://github.com/AgoraIO/skills "$dir"; then
  echo "agora skills synced into $dir"
else
  echo "warning: could not fetch the Agora skills pack; continuing without it" >&2
fi
exit 0
