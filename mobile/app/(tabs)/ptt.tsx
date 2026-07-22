import { Feather } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';
import { File, Paths, UploadType } from 'expo-file-system';
import { LinearGradient } from 'expo-linear-gradient';
import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  Easing,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import {
  type AudioPlayer,
  AudioQuality,
  createAudioPlayer,
  IOSOutputFormat,
  type RecordingOptions,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
} from 'expo-audio';

import { AmbientBackground } from '../../components/AmbientBackground';
import { EmptyState } from '../../components/EmptyState';
import { Orb } from '../../components/Orb';
import { apiPost } from '../../lib/api';
import { base64ToUint8Array } from '../../lib/base64';
import { getPairing } from '../../lib/pairing';
import { accentGradient, accentOnColor, colors, ground, radii, spacing, typography } from '../../lib/theme';
import { isAskRepeat, type TextTurnResponse, type VoiceTurnResponse } from '../../lib/types';

// Recorded as uncompressed 16-bit PCM WAV on iOS specifically, so the
// upload never needs any transcoding and the server's /api/voice/turn
// (which parses the WAV header itself before handing off to parakeet-mlx)
// never has to special-case a compressed format. See mobile/README.md for
// why this was chosen over the default .m4a preset.
const WAV_RECORDING_OPTIONS: RecordingOptions = {
  extension: '.wav',
  sampleRate: 16000,
  numberOfChannels: 1,
  bitRate: 256000,
  android: {
    extension: '.wav',
    outputFormat: 'default',
    audioEncoder: 'default',
    sampleRate: 16000,
  },
  ios: {
    extension: '.wav',
    outputFormat: IOSOutputFormat.LINEARPCM,
    audioQuality: AudioQuality.MAX,
    sampleRate: 16000,
    linearPCMBitDepth: 16,
    linearPCMIsBigEndian: false,
    linearPCMIsFloat: false,
  },
  web: { mimeType: 'audio/wav', bitsPerSecond: 256000 },
};

type PttState = 'idle' | 'recording' | 'processing' | 'error';

type Turn = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  audioB64?: string;
};

export default function PttScreen() {
  const insets = useSafeAreaInsets();
  const recorder = useAudioRecorder(WAV_RECORDING_OPTIONS);
  const [state, setState] = useState<PttState>('idle');
  const [statusText, setStatusText] = useState('Hold to talk');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [micDisabled, setMicDisabled] = useState(false);
  const [composerText, setComposerText] = useState('');
  const [sending, setSending] = useState(false);
  const [composerError, setComposerError] = useState<string | null>(null);
  const elapsedTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const recordStart = useRef(0);
  const playerRef = useRef<AudioPlayer | null>(null);
  const listRef = useRef<FlatList<Turn>>(null);
  const composerInputRef = useRef<TextInput>(null);
  const pulse1 = useRef(new Animated.Value(0)).current;
  const pulse2 = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    return () => {
      if (elapsedTimer.current) clearInterval(elapsedTimer.current);
      playerRef.current?.remove();
    };
  }, []);

  useEffect(() => {
    if (state !== 'recording') {
      pulse1.stopAnimation();
      pulse2.stopAnimation();
      pulse1.setValue(0);
      pulse2.setValue(0);
      return;
    }
    const anim1 = Animated.loop(
      Animated.timing(pulse1, { toValue: 1, duration: 1400, easing: Easing.out(Easing.ease), useNativeDriver: true })
    );
    const anim2 = Animated.loop(
      Animated.sequence([
        Animated.delay(600),
        Animated.timing(pulse2, { toValue: 1, duration: 1400, easing: Easing.out(Easing.ease), useNativeDriver: true }),
      ])
    );
    anim1.start();
    anim2.start();
    return () => {
      anim1.stop();
      anim2.stop();
    };
  }, [state, pulse1, pulse2]);

  function addTurn(turn: Turn) {
    setTurns((prev) => [...prev, turn]);
    setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 50);
  }

  async function beginRecording() {
    if (state !== 'idle') return;

    const permission = await requestRecordingPermissionsAsync();
    if (!permission.granted) {
      setMicDisabled(true);
      setState('error');
      setStatusText('Microphone permission denied — enable it in Settings');
      return;
    }

    try {
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
    } catch (e) {
      setState('error');
      setStatusText(e instanceof Error ? e.message : 'Could not start recording');
      return;
    }

    setState('recording');
    recordStart.current = Date.now();
    elapsedTimer.current = setInterval(() => {
      const secs = ((Date.now() - recordStart.current) / 1000).toFixed(1);
      setStatusText(`Recording… ${secs}s`);
    }, 200);
  }

  async function finishRecording() {
    if (state !== 'recording') return;
    if (elapsedTimer.current) clearInterval(elapsedTimer.current);
    setState('processing');
    setStatusText('Transcribing…');

    try {
      await recorder.stop();
      const uri = recorder.uri;
      if (!uri) throw new Error('recording produced no file');

      const pairing = await getPairing();
      if (!pairing) throw new Error('not paired');

      const file = new File(uri);
      const result = await file.upload(`${pairing.serverUrl}/api/voice/turn`, {
        httpMethod: 'POST',
        uploadType: UploadType.MULTIPART,
        fieldName: 'audio',
        mimeType: 'audio/wav',
        headers: { Authorization: `Bearer ${pairing.token}` },
      });

      if (result.status < 200 || result.status >= 300) {
        throw new Error(`server returned ${result.status}: ${result.body.slice(0, 200)}`);
      }

      const data: VoiceTurnResponse = JSON.parse(result.body);

      if (isAskRepeat(data)) {
        setStatusText(`Didn't catch that — ${data.reason}`);
        setTimeout(() => setStatusText('Hold to talk'), 2500);
      } else {
        addTurn({ id: `${data.turn_id}-u`, role: 'user', text: data.transcript });
        addTurn({ id: `${data.turn_id}-a`, role: 'assistant', text: data.reply_text, audioB64: data.audio_b64 });
        setStatusText('Hold to talk');
        playReplyAudio(data.audio_b64);
        // Drop the transcript into the composer, editable — the pipeline
        // already ran and committed (side effects and all), so this is a
        // correction/follow-up affordance rather than a gate before send:
        // a mistranscription is common enough to fix, but re-running the
        // whole turn through /api/turn on every voice utterance (even
        // correctly-transcribed ones) would risk double-firing tool calls.
        setComposerText(data.transcript);
        setTimeout(() => composerInputRef.current?.focus(), 100);
      }
      setState('idle');
    } catch (e) {
      setState('error');
      setStatusText(e instanceof Error ? e.message : 'Voice turn failed');
      setTimeout(() => {
        setState('idle');
        setStatusText('Hold to talk');
      }, 2500);
    }
  }

  function cancelRecording() {
    if (state !== 'recording') return;
    if (elapsedTimer.current) clearInterval(elapsedTimer.current);
    recorder.stop().catch(() => {
      // best-effort — we're discarding this recording regardless
    });
    setState('idle');
    setStatusText('Hold to talk');
  }

  function playReplyAudio(base64Wav: string) {
    if (!base64Wav) return;
    try {
      const bytes = base64ToUint8Array(base64Wav);
      const tmpFile = new File(Paths.cache, `${Date.now()}-reply.wav`);
      tmpFile.create({ overwrite: true });
      tmpFile.write(bytes);

      playerRef.current?.remove();
      const player = createAudioPlayer(tmpFile.uri);
      playerRef.current = player;
      player.play();
    } catch {
      // playback failure is non-fatal — the transcript/reply text are already shown
    }
  }

  async function handleSend() {
    const text = composerText.trim();
    if (!text || sending) return;
    setSending(true);
    setComposerError(null);
    setComposerText('');
    try {
      const data = await apiPost<TextTurnResponse>('/api/turn', { text });
      addTurn({ id: `${data.turn_id}-u`, role: 'user', text });
      addTurn({ id: `${data.turn_id}-a`, role: 'assistant', text: data.reply_text });
    } catch (e) {
      setComposerText(text);
      setComposerError(e instanceof Error ? e.message : 'Failed to send');
      setTimeout(() => setComposerError(null), 3500);
    } finally {
      setSending(false);
    }
  }

  const isRecording = state === 'recording';
  const isProcessing = state === 'processing';
  const isError = state === 'error';

  return (
    <View style={styles.root}>
      <AmbientBackground />
      <KeyboardAvoidingView style={styles.flexFill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={[styles.container, { paddingTop: insets.top }]}>
          <Text style={styles.greet}>Listening</Text>

          <View style={styles.orbTouchArea}>
            {isRecording ? (
              <>
                <Animated.View
                  style={[
                    styles.pulseRing,
                    {
                      opacity: pulse1.interpolate({ inputRange: [0, 1], outputRange: [0.5, 0] }),
                      transform: [{ scale: pulse1.interpolate({ inputRange: [0, 1], outputRange: [1, 1.6] }) }],
                    },
                  ]}
                />
                <Animated.View
                  style={[
                    styles.pulseRing,
                    {
                      opacity: pulse2.interpolate({ inputRange: [0, 1], outputRange: [0.5, 0] }),
                      transform: [{ scale: pulse2.interpolate({ inputRange: [0, 1], outputRange: [1, 1.6] }) }],
                    },
                  ]}
                />
              </>
            ) : null}
            <Pressable
              disabled={micDisabled}
              onPressIn={beginRecording}
              onPressOut={finishRecording}
              onTouchCancel={cancelRecording}
              hitSlop={12}
              style={micDisabled && styles.orbDisabled}
            >
              <Orb size={148} />
              {isProcessing ? (
                <View style={styles.orbSpinner}>
                  <ActivityIndicator color={colors.ink} />
                </View>
              ) : null}
            </Pressable>
          </View>

          <Text style={[styles.statusLabel, isError && styles.statusLabelError]}>{statusText}</Text>

          <View style={styles.conversation}>
            {turns.length === 0 ? (
              <EmptyState
                icon="mic"
                title="Nala is here"
                subtitle="Hold the orb and say what's on your mind, or type below."
              />
            ) : (
              <FlatList
                ref={listRef}
                data={turns}
                keyExtractor={(t) => t.id}
                contentContainerStyle={styles.listContent}
                renderItem={({ item }) => (
                  <View style={[styles.bubbleRow, item.role === 'user' ? styles.bubbleRowUser : styles.bubbleRowAssistant]}>
                    <View style={[styles.bubble, item.role === 'user' ? styles.bubbleUser : styles.bubbleAssistant]}>
                      <Text style={styles.bubbleText}>{item.text}</Text>
                      {item.role === 'assistant' && item.audioB64 ? (
                        <Pressable style={styles.replayBtn} onPress={() => playReplyAudio(item.audioB64 as string)} hitSlop={8}>
                          <View style={styles.replayIconWrap}>
                            <Feather name="volume-2" size={12} color="#c4b5fd" />
                          </View>
                          <Text style={styles.replayText}>Replay reply</Text>
                        </Pressable>
                      ) : null}
                    </View>
                  </View>
                )}
              />
            )}
          </View>

          <View style={[styles.composerOuter, { marginBottom: insets.bottom + spacing.sm }]}>
            {composerError ? <Text style={styles.composerErrorText}>{composerError}</Text> : null}
            <View style={styles.composer}>
              <BlurView intensity={40} tint="dark" style={StyleSheet.absoluteFill} />
              <TextInput
                ref={composerInputRef}
                style={styles.composerInput}
                value={composerText}
                onChangeText={setComposerText}
                placeholder="Type to correct, or hold the orb…"
                placeholderTextColor={colors.faint}
                editable={!sending}
                multiline
                onSubmitEditing={handleSend}
                returnKeyType="send"
                blurOnSubmit
              />
              <Pressable
                disabled={micDisabled}
                onPressIn={beginRecording}
                onPressOut={finishRecording}
                onTouchCancel={cancelRecording}
                hitSlop={8}
                style={styles.micBtn}
              >
                <Feather name="mic" size={16} color="#c4b5fd" />
              </Pressable>
              <Pressable onPress={handleSend} disabled={sending || !composerText.trim()} hitSlop={8}>
                <LinearGradient
                  colors={accentGradient}
                  start={{ x: 0, y: 0 }}
                  end={{ x: 1, y: 1 }}
                  style={[styles.sendBtn, (sending || !composerText.trim()) && styles.sendBtnDisabled]}
                >
                  {sending ? (
                    <ActivityIndicator size="small" color={accentOnColor} />
                  ) : (
                    <Feather name="send" size={15} color={accentOnColor} />
                  )}
                </LinearGradient>
              </Pressable>
            </View>
          </View>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ground.bottom, overflow: 'hidden' },
  flexFill: { flex: 1 },
  container: { flex: 1, paddingHorizontal: spacing.lg, alignItems: 'center' },
  greet: {
    fontSize: 12,
    letterSpacing: 4,
    textTransform: 'uppercase',
    color: '#9a91c4',
    fontWeight: '600',
    marginTop: spacing.sm,
  },
  orbTouchArea: { width: 220, height: 220, alignItems: 'center', justifyContent: 'center' },
  pulseRing: {
    position: 'absolute',
    width: 184,
    height: 184,
    borderRadius: 92,
    borderWidth: 2,
    borderColor: '#7dd3fc',
  },
  orbDisabled: { opacity: 0.4 },
  orbSpinner: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, alignItems: 'center', justifyContent: 'center' },
  statusLabel: { fontSize: 13, fontWeight: '600', color: '#c4b5fd', letterSpacing: 0.3, marginTop: spacing.xs },
  statusLabelError: { color: colors.amber },
  conversation: { flex: 1, width: '100%', marginTop: spacing.md },
  listContent: { paddingVertical: spacing.base, gap: spacing.md },
  bubbleRow: { flexDirection: 'row' },
  bubbleRowUser: { justifyContent: 'flex-end' },
  bubbleRowAssistant: { justifyContent: 'flex-start' },
  bubble: { maxWidth: '88%', borderRadius: radii.xl, padding: spacing.md, gap: spacing.xs },
  bubbleUser: {
    backgroundColor: 'rgba(167,139,250,0.2)',
    borderColor: 'rgba(167,139,250,0.35)',
    borderWidth: 1,
    borderBottomRightRadius: 6,
  },
  bubbleAssistant: {
    backgroundColor: colors.panel2,
    borderColor: colors.hair,
    borderTopColor: 'rgba(255,255,255,0.2)',
    borderWidth: 1,
    borderBottomLeftRadius: 6,
  },
  bubbleText: { ...typography.body, lineHeight: 20 },
  replayBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, marginTop: spacing.xs },
  replayIconWrap: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: 'rgba(196,181,253,0.16)',
    borderWidth: 1,
    borderColor: 'rgba(196,181,253,0.3)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  replayText: { color: '#c4b5fd', fontSize: 12, fontWeight: '600' },
  composerOuter: { width: '100%' },
  composerErrorText: { color: colors.amber, fontSize: 12, marginBottom: spacing.xs, textAlign: 'center' },
  composer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: spacing.sm,
    borderRadius: radii.xxl,
    borderWidth: 1,
    borderColor: colors.hair,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
    paddingLeft: spacing.base,
    overflow: 'hidden',
  },
  composerInput: {
    flex: 1,
    color: colors.ink,
    fontSize: 14,
    maxHeight: 100,
    paddingVertical: Platform.OS === 'ios' ? spacing.sm : 0,
  },
  micBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderWidth: 1,
    borderColor: colors.hair,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendBtn: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center' },
  sendBtnDisabled: { opacity: 0.5 },
});
