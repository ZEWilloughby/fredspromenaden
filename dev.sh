#!/bin/bash
export NVM_DIR="$HOME/.nvm"
# shellcheck source=/dev/null
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
nvm use 20.19.6 >/dev/null
cd "$(dirname "$0")"
exec npm run dev -- --host
