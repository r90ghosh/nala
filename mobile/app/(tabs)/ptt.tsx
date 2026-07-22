import { Feather } from '@expo/vector-icons';
import { File, Paths } from 'expo-file-system';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Animated, Easing, FlatList, Pressable, StyleSheet, Text, View } from 'react-native';
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

import { EmptyState } from '../../components/EmptyState';
import { base64ToUint8Array } from '../../lib/base64';
import { getPairing } from '../../lib/pairing';
import { colors, radii, spacing, typography } from '../../lib/theme';
import { isAskRepeat, type VoiceTurnResponse } from '../../lib/types';

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
  const elapsedTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const recordStart = useRef(0);
  const playerRef = useRef<AudioPlayer | null>(null);
  const listRef = useRef<FlatList<Turn>>(null);
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

  const isRecording = state === 'recording';
  const isProcessing = state === 'processing';
  const isError = state === 'error';

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {turns.length === 0 ? (
        <EmptyState
          icon="mic"
          title="Press and hold to talk"
          subtitle="Hold the button below, say what's on your mind, and release — Nala replies out loud."
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
                    <Feather name="volume-2" size={14} color={colors.accent} />
                    <Text style={styles.replayText}>Replay</Text>
                  </Pressable>
                ) : null}
              </View>
            </View>
          )}
        />
      )}

      <View style={[styles.dock, { paddingBottom: insets.bottom + spacing.base }]}>
        <Text style={[styles.statusText, isError && styles.statusError]}>{statusText}</Text>
        <View style={styles.pttWrap}>
          {isRecording ? (
            <>
              <Animated.View
                style={[
                  styles.pulseRing,
                  {
                    opacity: pulse1.interpolate({ inputRange: [0, 1], outputRange: [0.45, 0] }),
                    transform: [{ scale: pulse1.interpolate({ inputRange: [0, 1], outputRange: [1, 1.9] }) }],
                  },
                ]}
              />
              <Animated.View
                style={[
                  styles.pulseRing,
                  {
                    opacity: pulse2.interpolate({ inputRange: [0, 1], outputRange: [0.45, 0] }),
                    transform: [{ scale: pulse2.interpolate({ inputRange: [0, 1], outputRange: [1, 1.9] }) }],
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
            style={[
              styles.pttButton,
              isRecording && styles.pttButtonRecording,
              isProcessing && styles.pttButtonProcessing,
              isError && styles.pttButtonError,
              micDisabled && styles.pttButtonDisabled,
            ]}
          >
            {isProcessing ? (
              <ActivityIndicator color={colors.accent} />
            ) : (
              <Feather name="mic" size={44} color={isRecording ? colors.red : colors.accent} />
            )}
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.base },
  listContent: { padding: spacing.base, gap: spacing.md },
  bubbleRow: { flexDirection: 'row' },
  bubbleRowUser: { justifyContent: 'flex-end' },
  bubbleRowAssistant: { justifyContent: 'flex-start' },
  bubble: { maxWidth: '85%', borderRadius: radii.lg, padding: spacing.md, gap: spacing.xs },
  bubbleUser: {
    backgroundColor: 'rgba(56,189,248,0.12)',
    borderColor: 'rgba(56,189,248,0.28)',
    borderWidth: 1,
    borderTopRightRadius: 4,
  },
  bubbleAssistant: {
    backgroundColor: colors.panel2,
    borderColor: colors.hair,
    borderWidth: 1,
    borderTopLeftRadius: 4,
  },
  bubbleText: { ...typography.body, lineHeight: 20 },
  replayBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, marginTop: spacing.xs },
  replayText: { color: colors.accent, fontSize: 12, fontWeight: '600' },
  dock: {
    alignItems: 'center',
    paddingTop: spacing.lg,
    borderTopColor: colors.hair,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  statusText: { ...typography.caption, marginBottom: spacing.md },
  statusError: { color: colors.amber },
  pttWrap: { width: 150, height: 150, alignItems: 'center', justifyContent: 'center' },
  pulseRing: {
    position: 'absolute',
    width: 120,
    height: 120,
    borderRadius: 60,
    borderWidth: 2,
    borderColor: colors.red,
  },
  pttButton: {
    width: 120,
    height: 120,
    borderRadius: 60,
    borderWidth: 2,
    borderColor: colors.hair,
    backgroundColor: colors.panel2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pttButtonRecording: { borderColor: colors.red, backgroundColor: 'rgba(248,113,113,0.14)' },
  pttButtonProcessing: { borderColor: colors.accent, backgroundColor: 'rgba(56,189,248,0.14)' },
  pttButtonError: { borderColor: colors.amber, backgroundColor: 'rgba(251,191,36,0.12)' },
  pttButtonDisabled: { opacity: 0.4 },
});
