#!/usr/bin/env bash
# Rejects bare `except:` in nala/ — the only sanctioned way to catch an
# exception in the action path is `except Exception as exc:` inside a
# `with loud_failure(...)` block (see nala/errors.py). Also flags (best
# effort) `except Exception:` blocks whose body is just `pass` — a silent
# swallow disguised as handling.
set -euo pipefail

cd "$(dirname "$0")/.."

BARE=$(grep -rnE '^\s*except\s*:' nala/ || true)

if [ -n "$BARE" ]; then
    echo "Bare 'except:' is banned in the action path (nala/). Use 'except Exception as exc:' inside a loud_failure(...) block instead." >&2
    echo "$BARE" >&2
    exit 1
fi

SWALLOWED=$(grep -rn -A1 -E '^[[:space:]]*except Exception([[:space:]]+as[[:space:]]+[A-Za-z_][A-Za-z0-9_]*)?[[:space:]]*:[[:space:]]*$' nala/ | awk '
    /^[^:]+:[0-9]+:/ { match_line = $0; pending = 1; next }
    /^[^-]+-[0-9]+-/ {
        if (pending) {
            content = $0
            sub(/^[^-]+-[0-9]+-/, "", content)
            gsub(/^[ \t]+|[ \t]+$/, "", content)
            if (content == "pass") print match_line
        }
        pending = 0
        next
    }
    { pending = 0 }
')

if [ -n "$SWALLOWED" ]; then
    echo "except Exception: block whose body is just 'pass' is banned in the action path (nala/) — that silently swallows failures. Log via loud_failure(...) instead." >&2
    echo "$SWALLOWED" >&2
    exit 1
fi

echo "lint_action_path: OK — no bare except: or pass-only except Exception: found in nala/"
