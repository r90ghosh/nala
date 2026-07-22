/**
 * Server URL + access token, persisted in expo-secure-store (iOS Keychain-
 * backed). Never committed, never logged — this is the one secret the app
 * holds, and it's what stands in for the web client's cookie/Origin gate
 * (see nala/auth.py's is_bearer_authenticated).
 */
import * as SecureStore from 'expo-secure-store';

const SERVER_URL_KEY = 'nala_server_url';
const ACCESS_TOKEN_KEY = 'nala_access_token';

export type PairingInfo = {
  serverUrl: string;
  token: string;
};

export async function getPairing(): Promise<PairingInfo | null> {
  const [serverUrl, token] = await Promise.all([
    SecureStore.getItemAsync(SERVER_URL_KEY),
    SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
  ]);
  if (!serverUrl || !token) return null;
  return { serverUrl, token };
}

export async function savePairing(info: PairingInfo): Promise<void> {
  await Promise.all([
    SecureStore.setItemAsync(SERVER_URL_KEY, info.serverUrl),
    SecureStore.setItemAsync(ACCESS_TOKEN_KEY, info.token),
  ]);
}

export async function clearPairing(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(SERVER_URL_KEY),
    SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
  ]);
}
