#!/usr/bin/env bash
# Rejects bare `except:` in nala/ — the only sanctioned way to catch an
# exception in the action path is `except Exception as exc:` inside a
# `with loud_failure(...)` block (see nala/errors.py).
set -euo pipefail

cd "$(dirname "$0")/.."

MATCHES=$(grep -rnE '^\s*except\s*:' nala/ || true)

if [ -n "$MATCHES" ]; then
    echo "Bare 'except:' is banned in the action path (nala/). Use 'except Exception as exc:' inside a loud_failure(...) block instead." >&2
    echo "$MATCHES" >&2
    exit 1
fi

echo "lint_action_path: OK — no bare except: found in nala/"
