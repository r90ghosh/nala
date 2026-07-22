# Nala — iOS app (Expo)

A native companion to the web Mission Control UI: feed, push-to-talk, and
the action queue, talking directly to the same `nala.serve` on the Mac
(or over the `com.nala.tunnel` cloudflared tunnel for a real device). See
the repo root's `PLAN.md` ("Clients") and `CLAUDE.md` for the wider project.

## Requirements

- Node 18+ (this was built and tested against Node 26).
- Xcode + an iOS Simulator (for `npx expo start` → press `i`).
- A running `nala.serve` instance — from the repo root:
  `.venv/bin/python -m nala.serve` (binds `127.0.0.1:8642`).

## Run it

```bash
cd mobile
npm install         # .npmrc already sets legacy-peer-deps=true (expo-router's
                     # web-support deps have an upstream peer conflict irrelevant to iOS)
npx expo start
```

Then press `i` to launch the iOS Simulator, or scan the QR code with a
physical device's Camera app (Expo Go) — though a physical device should
pair against the tunnel URL, not `127.0.0.1` (see below).

**First launch** asks you to pair: a server URL (defaults to
`http://127.0.0.1:8642`, which the Simulator can reach directly since it
shares the Mac's localhost) and the access token (`NALA_ACCESS_TOKEN` from
the repo root's `.env`). Pairing validates by hitting `GET /api/health`
before saving anything, so a wrong URL/token never gets persisted.

For a **real device**, pair against the current cloudflared tunnel URL
instead of `127.0.0.1` — the device isn't on the Mac's localhost.

## Verify the networking contract without the Simulator

Useful when iterating on the server side, or just to confirm the API
contract holds before booting Xcode at all:

```bash
npx tsx scripts/verify-api.ts --url http://127.0.0.1:8642 --token <NALA_ACCESS_TOKEN>
```

Hits `/api/health`, `/api/events`, `/api/actions`, `/api/purposes`,
`/api/memory`, and the bearer-token CSRF-bypass path against a real running
server and checks the response shapes.

## How auth works here

The app is a non-browser client — no session cookie to hold the way a
browser does. It authenticates every request with
`Authorization: Bearer <token>` instead. The server
(`nala/auth.py::is_bearer_authenticated`) treats a valid bearer token as
sufficient on its own: it stands in for the cookie on tunnel requests, and
it bypasses the CSRF Origin allow-list on state-changing requests (a bearer
token can't be silently replayed by a malicious webpage the way a cookie
can, since nothing attaches it automatically — only code that already
holds the secret, i.e. this app reading it back out of secure-store, can
produce one).

The token and server URL are stored via `expo-secure-store` (iOS Keychain-
backed) — never committed, never logged, never lives in a plain-text
config file.

## Push-to-talk audio format

Recorded as **uncompressed 16-bit PCM WAV** (`RecordingOptions.ios.outputFormat:
IOSOutputFormat.LINEARPCM`), not the default `.m4a`/AAC preset — this
avoids needing any transcoding, client- or server-side: `nala.serve`'s
`/api/voice/turn` parses the WAV header directly (via Python's `wave`
module) before ever handing the file to parakeet-mlx, and that parsing
step only understands actual WAV files. If a future format change is
needed here, the alternative is teaching the server to probe the format
with `ffprobe` instead of `wave.open()` — parakeet-mlx's own loader already
shells out to `ffmpeg` and can handle any format ffmpeg does; only the
server's own pre-transcribe validation is WAV-specific right now.

**Not yet verified against real microphone input** — this was built and
verified for API-shape and TypeScript/bundle correctness (see "What's
verified" below), but actually pressing the PTT button and confirming the
recorded audio round-trips correctly through STT needs a live Simulator
session with real mic input, which is the next verification step.

## What's verified vs. what needs the Simulator

Verified from this environment (no Simulator/Xcode UI available here):
- `npx tsc --noEmit` — clean.
- `npx expo-doctor` — 19/20 (the one failure is a stray, unrelated
  `~/node_modules` react install outside this repo entirely — see below).
- Metro successfully bundles the iOS entry point (1285 modules, no errors).
- The full networking contract (`scripts/verify-api.ts`) against a live,
  running `nala.serve` — including the bearer-token CSRF-bypass path.

Needs a real Simulator session (mic input, on-screen interaction):
- PTT recording → upload → transcript → reply audio round-trip.
- Onboarding screen's actual look/feel and keyboard behavior.
- Tab navigation, action-queue swipe/confirm feel, scroll performance.

## Known environment quirk (not part of this project)

`expo-doctor` flags a duplicate `react` install: `node_modules/react@19.2.3`
(correct, local) vs. `../../../node_modules/react@19.0.0`. That second path
resolves to `/Users/<user>/node_modules` — a stray, unrelated install in
the home directory from some other project, dated well before this one
existed. Not touched here since it's outside this repo; flagged in case it
ever causes a native build resolution issue.

## Project layout

```
mobile/
  app/                 # expo-router file-based routes
    _layout.tsx         # pairing gate (redirects to /onboarding if unpaired)
    onboarding.tsx       # server URL + token entry, validates via GET /api/health
    (tabs)/
      _layout.tsx         # bottom tab bar
      index.tsx            # Feed — polls GET /api/events
      ptt.tsx               # push-to-talk hero screen
      actions.tsx           # action queue — GET /api/actions, confirm/reject
      memory.tsx            # memory node list — GET /api/memory
  lib/
    api.ts             # fetch wrapper (bearer auth)
    pairing.ts          # secure-store get/set/clear
    PairingContext.tsx   # shared pairing state (layout + onboarding agree)
    theme.ts            # colors matching nala/static/style.css
    types.ts             # mirrors nala/serve.py's JSON contracts
    base64.ts             # hand-rolled base64 decoder (no atob/btoa in RN)
  scripts/
    verify-api.ts       # networking contract check against a live server
```
