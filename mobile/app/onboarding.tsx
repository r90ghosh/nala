import { Feather } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AmbientBackground } from '../components/AmbientBackground';
import { Button } from '../components/Button';
import { Orb } from '../components/Orb';
import { validatePairing } from '../lib/api';
import { usePairingContext } from '../lib/PairingContext';
import { savePairing } from '../lib/pairing';
import { colors, ground, radii, spacing, typography } from '../lib/theme';

// Simulator default — the Simulator can reach the Mac's own localhost
// directly. A real device needs the tunnel URL instead (https://…), which
// the user pastes in over this default.
const DEFAULT_SERVER_URL = 'http://127.0.0.1:8642';

export default function OnboardingScreen() {
  const insets = useSafeAreaInsets();
  const [serverUrl, setServerUrl] = useState(DEFAULT_SERVER_URL);
  const [token, setToken] = useState('');
  const [tokenVisible, setTokenVisible] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { markPaired } = usePairingContext();

  async function handlePaste() {
    const clip = await Clipboard.getStringAsync();
    if (clip) setToken(clip.trim());
  }

  async function handlePair() {
    setError(null);
    const trimmedUrl = serverUrl.trim().replace(/\/+$/, '');
    const trimmedToken = token.trim();
    if (!trimmedUrl || !trimmedToken) {
      setError('Server URL and access token are both required.');
      return;
    }

    setChecking(true);
    const ok = await validatePairing(trimmedUrl, trimmedToken);
    setChecking(false);

    if (!ok) {
      setError("Couldn't reach the server with that URL and token. Double-check both and try again.");
      return;
    }

    await savePairing({ serverUrl: trimmedUrl, token: trimmedToken });
    markPaired();
  }

  return (
    <View style={styles.root}>
      <AmbientBackground />
      <KeyboardAvoidingView
        style={[styles.container, { paddingTop: insets.top, paddingBottom: insets.bottom + spacing.xl }]}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
      <View style={styles.content}>
        <View style={styles.hero}>
          <Orb size={94} showRings={false} />
          <Text style={styles.wordmark}>Wake Nala</Text>
          <Text style={styles.tagline}>Connect to the server on your Mac, and Nala comes alive on this device.</Text>
        </View>

        <View style={styles.form}>
          <Text style={typography.section}>Server URL</Text>
          <TextInput
            style={[styles.input, { marginTop: spacing.xs }]}
            value={serverUrl}
            onChangeText={setServerUrl}
            placeholder={DEFAULT_SERVER_URL}
            placeholderTextColor={colors.faint}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
          />

          <Text style={[typography.section, { marginTop: spacing.lg }]}>Access token</Text>
          <View style={[styles.inputRow, { marginTop: spacing.xs }]}>
            <TextInput
              style={[styles.input, styles.tokenInput, typography.mono]}
              value={token}
              onChangeText={setToken}
              placeholder="paste your NALA_ACCESS_TOKEN"
              placeholderTextColor={colors.faint}
              autoCapitalize="none"
              autoCorrect={false}
              secureTextEntry={!tokenVisible}
            />
            <Pressable style={styles.inlineIconBtn} onPress={() => setTokenVisible((v) => !v)} hitSlop={10}>
              <Feather name={tokenVisible ? 'eye-off' : 'eye'} size={18} color={colors.mute} />
            </Pressable>
            <Pressable style={styles.pasteBtn} onPress={handlePaste} hitSlop={10}>
              <Feather name="clipboard" size={14} color={colors.accent} />
              <Text style={styles.pasteBtnText}>Paste</Text>
            </Pressable>
          </View>

          {error ? (
            <View style={styles.errorBox}>
              <Feather name="alert-triangle" size={14} color={colors.red} />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          <Button label="Pair" onPress={handlePair} loading={checking} style={{ marginTop: spacing.xl }} />

          <View style={styles.secure}>
            <Feather name="lock" size={13} color={colors.faint} />
            <Text style={styles.secureText}>Stays on your local network</Text>
          </View>
        </View>
      </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ground.bottom, overflow: 'hidden' },
  container: { flex: 1 },
  content: { flex: 1, justifyContent: 'center', paddingHorizontal: spacing.xl, gap: spacing.xxl },
  hero: { alignItems: 'center', gap: spacing.sm },
  wordmark: { ...typography.display, fontSize: 27, marginTop: spacing.xs },
  tagline: { ...typography.body, color: colors.mute, textAlign: 'center' },
  form: { width: '100%' },
  input: {
    backgroundColor: colors.panel2,
    borderColor: colors.hair,
    borderTopColor: 'rgba(255,255,255,0.22)',
    borderWidth: 1,
    borderRadius: radii.lg,
    padding: spacing.md,
    color: colors.ink,
    fontSize: 15,
    minHeight: 48,
  },
  inputRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  tokenInput: { flex: 1 },
  inlineIconBtn: { padding: spacing.xs },
  pasteBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: 'rgba(167,139,250,0.14)',
    borderColor: 'rgba(167,139,250,0.35)',
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
  },
  pasteBtnText: { color: colors.accent, fontSize: 12, fontWeight: '700' },
  errorBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    backgroundColor: 'rgba(248,113,113,0.1)',
    borderColor: 'rgba(248,113,113,0.3)',
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    marginTop: spacing.lg,
  },
  errorText: { color: colors.red, fontSize: 13, lineHeight: 18, flex: 1 },
  secure: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.xs, marginTop: spacing.lg },
  secureText: { color: colors.faint, fontSize: 11.5 },
});
