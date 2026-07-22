#!/usr/bin/env -S npx tsx
/**
 * Verifies the networking contract the app relies on against a REAL running
 * `nala.serve` instance, before ever touching the Simulator. Run with:
 *
 *   npx tsx scripts/verify-api.ts --url http://127.0.0.1:8642 --token <NALA_ACCESS_TOKEN>
 *
 * Exits non-zero if any check fails.
 */

type CheckResult = { name: string; ok: boolean; detail: string };

function parseArgs(): { url: string; token: string } {
  const args = process.argv.slice(2);
  let url = 'http://127.0.0.1:8642';
  let token = process.env.NALA_ACCESS_TOKEN || '';

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--url') url = args[++i];
    else if (args[i] === '--token') token = args[++i];
  }

  if (!token) {
    console.error('Usage: npx tsx scripts/verify-api.ts --url <server> --token <token>');
    console.error('(or set NALA_ACCESS_TOKEN in the environment)');
    process.exit(1);
  }
  return { url: url.replace(/\/+$/, ''), token };
}

async function main() {
  const { url, token } = parseArgs();
  const authHeaders = { Authorization: `Bearer ${token}` };
  const results: CheckResult[] = [];

  async function check(name: string, fn: () => Promise<void>) {
    try {
      await fn();
      results.push({ name, ok: true, detail: 'ok' });
    } catch (e) {
      results.push({ name, ok: false, detail: e instanceof Error ? e.message : String(e) });
    }
  }

  // Bearer auth must work on a bare GET, same as the app's onboarding
  // health-check does before it ever saves credentials.
  await check('GET /api/health (bearer auth)', async () => {
    const resp = await fetch(`${url}/api/health`, { headers: authHeaders });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (!('ollama_reachable' in data)) throw new Error('missing ollama_reachable field');
  });

  await check('GET /api/health with WRONG token is rejected', async () => {
    // Only meaningful over the tunnel (local dev traffic bypasses auth
    // entirely) — still worth confirming the endpoint doesn't 500 either way.
    const resp = await fetch(`${url}/api/health`, { headers: { Authorization: 'Bearer definitely-wrong' } });
    if (resp.status >= 500) throw new Error(`unexpected 5xx: ${resp.status}`);
  });

  await check('GET /api/events shape', async () => {
    const resp = await fetch(`${url}/api/events?since=0`, { headers: authHeaders });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (!Array.isArray(data)) throw new Error('expected an array');
    if (data.length && !('type' in data[0])) throw new Error('event row missing "type"');
  });

  await check('GET /api/actions shape', async () => {
    const resp = await fetch(`${url}/api/actions`, { headers: authHeaders });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (!Array.isArray(data)) throw new Error('expected an array');
  });

  await check('GET /api/purposes shape', async () => {
    const resp = await fetch(`${url}/api/purposes`, { headers: authHeaders });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (!Array.isArray(data) || data.length !== 8) throw new Error('expected 8 purposes');
    if (!('risk_profile' in data[0])) throw new Error('purpose row missing "risk_profile"');
  });

  await check('GET /api/memory shape', async () => {
    const resp = await fetch(`${url}/api/memory`, { headers: authHeaders });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (!('nodes' in data) || !('edges' in data) || !('observations' in data)) {
      throw new Error('missing nodes/edges/observations');
    }
  });

  // Bearer token must bypass the CSRF origin gate on a state-changing
  // request with NO Origin header at all — this is the whole point of using
  // bearer auth for a native client instead of trying to spoof Origin.
  await check('POST /api/actions/<bad-token>/reject with bearer, no Origin, is not 403', async () => {
    const resp = await fetch(`${url}/api/actions/deadbeef/reject`, {
      method: 'POST',
      headers: authHeaders,
    });
    if (resp.status === 403) throw new Error('got 403 — bearer token did not bypass the CSRF gate');
  });

  await check('POST with bearer + no Origin is rejected without a valid token', async () => {
    const resp = await fetch(`${url}/api/actions/deadbeef/reject`, {
      method: 'POST',
      headers: { Authorization: 'Bearer definitely-wrong' },
    });
    if (resp.status !== 403) throw new Error(`expected 403 (falls through to the Origin gate), got ${resp.status}`);
  });

  let allOk = true;
  for (const r of results) {
    console.log(`${r.ok ? '✅' : '❌'} ${r.name}${r.ok ? '' : ` — ${r.detail}`}`);
    if (!r.ok) allOk = false;
  }

  process.exit(allOk ? 0 : 1);
}

main();
