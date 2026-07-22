import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { validatePairing } from '../lib/api';
import { usePairingContext } from '../lib/PairingContext';
import { savePairing } from '../lib/pairing';
import { colors } from '../lib/theme';

// Simulator default — the Simulator can reach the Mac's own localhost
// directly. A real device needs the tunnel URL instead (https://…), which
// the user pastes in over this default.
const DEFAULT_SERVER_URL = 'http://127.0.0.1:8642';

export default function OnboardingScreen() {
  const [serverUrl, setServerUrl] = useState(DEFAULT_SERVER_URL);
  const [token, setToken] = useState('');
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { markPaired } = usePairingContext();

  async function handlePair() {
    setError(null);
    const trimmedUrl = serverUrl.trim().replace(/\/+$/, '');
    const trimmedToken = token.trim();
    if (!trimmedUrl || !trimmedToken) {
      setError('server URL and access token are both required');
      return;
    }

    setChecking(true);
    const ok = await validatePairing(trimmedUrl, trimmedToken);
    setChecking(false);

    if (!ok) {
      setError("couldn't reach the server with that URL/token — check both and try again");
      return;
    }

    await savePairing({ serverUrl: trimmedUrl, token: trimmedToken });
    markPaired();
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <Text style={styles.title}>Nala</Text>
      <Text style={styles.subtitle}>Pair with your Mac server</Text>

      <Text style={styles.label}>Server URL</Text>
      <TextInput
        style={styles.input}
        value={serverUrl}
        onChangeText={setServerUrl}
        placeholder={DEFAULT_SERVER_URL}
        placeholderTextColor={colors.faint}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
      />

      <Text style={styles.label}>Access token</Text>
      <TextInput
        style={styles.input}
        value={token}
        onChangeText={setToken}
        placeholder="paste your NALA_ACCESS_TOKEN"
        placeholderTextColor={colors.faint}
        autoCapitalize="none"
        autoCorrect={false}
        secureTextEntry
      />

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <Pressable
        style={({ pressed }) => [styles.button, pressed && styles.buttonPressed]}
        onPress={handlePair}
        disabled={checking}
      >
        {checking ? (
          <ActivityIndicator color={colors.base} />
        ) : (
          <Text style={styles.buttonText}>Pair</Text>
        )}
      </Pressable>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.base, padding: 24, justifyContent: 'center' },
  title: { color: '#fff', fontSize: 34, fontWeight: '700', marginBottom: 4 },
  subtitle: { color: colors.mute, fontSize: 14, marginBottom: 32 },
  label: {
    color: colors.mute,
    fontSize: 11,
    marginBottom: 6,
    marginTop: 18,
    textTransform: 'uppercase',
    letterSpacing: 1,
    fontWeight: '600',
  },
  input: {
    backgroundColor: colors.panel2,
    borderColor: colors.hair,
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    color: colors.ink,
    fontSize: 15,
  },
  error: { color: colors.red, marginTop: 18, fontSize: 13, lineHeight: 18 },
  button: {
    backgroundColor: colors.accent,
    borderRadius: 8,
    padding: 15,
    alignItems: 'center',
    marginTop: 28,
    minHeight: 48,
    justifyContent: 'center',
  },
  buttonPressed: { opacity: 0.85 },
  buttonText: { color: colors.base, fontWeight: '700', fontSize: 15 },
});
