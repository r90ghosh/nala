/**
 * Fetch wrapper for the paired Mac server. Authenticates via
 * `Authorization: Bearer <token>` — the app is a non-browser client with no
 * session cookie to hold, and a bearer token doubles as its own CSRF
 * defense (see nala/auth.py's is_bearer_authenticated for why). Every
 * mutating call must carry this header for nala.serve's origin gate to let
 * it through; GET calls need it too once traffic is going over the tunnel
 * (tunnel traffic requires either the cookie a browser has or this bearer
 * token — the app has only the latter).
 */
import { getPairing } from './pairing';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function safeErrorText(resp: Response): Promise<string> {
  try {
    const body = await resp.text();
    return body || `HTTP ${resp.status}`;
  } catch {
    return `HTTP ${resp.status}`;
  }
}

async function requirePairing(): Promise<{ serverUrl: string; token: string }> {
  const pairing = await getPairing();
  if (!pairing) throw new ApiError(0, 'not paired — pair with a server first');
  return pairing;
}

export async function apiGet<T>(path: string): Promise<T> {
  const { serverUrl, token } = await requirePairing();
  const resp = await fetch(`${serverUrl}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) throw new ApiError(resp.status, await safeErrorText(resp));
  return resp.json();
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const { serverUrl, token } = await requirePairing();
  const resp = await fetch(`${serverUrl}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) throw new ApiError(resp.status, await safeErrorText(resp));
  return resp.json();
}

/** Pairing validation: hits the server BEFORE anything is saved to
 * secure-store, so onboarding never persists credentials that don't work. */
export async function validatePairing(serverUrl: string, token: string): Promise<boolean> {
  try {
    const resp = await fetch(`${serverUrl}/api/health`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return resp.ok;
  } catch {
    return false;
  }
}
