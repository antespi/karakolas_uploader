# Source this file: `source activate.sh` or `. activate.sh`
# Loads project environment for granel.

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    echo "Error: this script must be sourced, not executed." >&2
    echo "Usage: source activate.sh" >&2
    exit 1
fi

GRANEL_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export GRANEL_ROOT

# Node binaries from local install (agent-browser, etc.)
if [ -d "$GRANEL_ROOT/node_modules/.bin" ]; then
    case ":$PATH:" in
        *":$GRANEL_ROOT/node_modules/.bin:"*) ;;
        *) export PATH="$GRANEL_ROOT/node_modules/.bin:$PATH" ;;
    esac
fi

# Python venv (created on demand)
if [ -d "$GRANEL_ROOT/.venv" ]; then
    # shellcheck disable=SC1091
    . "$GRANEL_ROOT/.venv/bin/activate"
fi

# Load .env if present (KEY=VALUE lines, no export needed)
if [ -f "$GRANEL_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$GRANEL_ROOT/.env"
    set +a
fi

echo "granel env loaded:"
echo "  GRANEL_ROOT=$GRANEL_ROOT"
command -v agent-browser >/dev/null && echo "  agent-browser: $(command -v agent-browser)"
command -v python >/dev/null && echo "  python: $(command -v python)"
