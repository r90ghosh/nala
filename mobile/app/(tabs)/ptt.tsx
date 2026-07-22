import { File, Paths } from 'expo-file-system';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

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

import { base64ToUint8Array } from '../../lib/base64';
import { getPairing } from '../../lib/pairing';
import { colors } from '../../lib/theme';
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

export default function PttScreen() {
  const recorder = useAudioRecorder(WAV_RECORDING_OPTIONS);
  const [state, setState] = useState<PttState>('idle');
  const [statusText, setStatusText] = useState('hold to talk');
  const [transcript, setTranscript] = useState<string | null>(null);
  const [replyText, setReplyText] = useState<string | null>(null);
  const [micDisabled, setMicDisabled] = useState(false);
  const elapsedTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const recordStart = useRef(0);
  const playerRef = useRef<AudioPlayer | null>(null);

  useEffect(() => {
    return () => {
      if (elapsedTimer.current) clearInterval(elapsedTimer.current);
      playerRef.current?.remove();
    };
  }, []);

  async function beginRecording() {
    if (state !== 'idle') return;

    const permission = await requestRecordingPermissionsAsync();
    if (!permission.granted) {
      setMicDisabled(true);
      setState('error');
      setStatusText('microphone permission denied — enable it in Settings');
      return;
    }

    try {
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
    } catch (e) {
      setState('error');
      setStatusText(e instanceof Error ? e.message : 'could not start recording');
      return;
    }

    setState('recording');
    setTranscript(null);
    setReplyText(null);
    recordStart.current = Date.now();
    elapsedTimer.current = setInterval(() => {
      const secs = ((Date.now() - recordStart.current) / 1000).toFixed(1);
      setStatusText(`recording… ${secs}s`);
    }, 200);
  }

  async function finishRecording() {
    if (state !== 'recording') return;
    if (elapsedTimer.current) clearInterval(elapsedTimer.current);
    setState('processing');
    setStatusText('transcribing…');

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
        setTranscript(data.transcript);
        setReplyText(null);
        setStatusText(`didn't catch that — ${data.reason}`);
      } else {
        setTranscript(data.transcript);
        setReplyText(data.reply_text);
        setStatusText('hold to talk');
        playReplyAudio(data.audio_b64);
      }
      setState('idle');
    } catch (e) {
      setState('error');
      setStatusText(e instanceof Error ? e.message : 'voice turn failed');
      setTimeout(() => {
        setState('idle');
        setStatusText('hold to talk');
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
    setStatusText('hold to talk');
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
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.transcriptArea}>
        {transcript ? (
          <View style={styles.bubbleUser}>
            <Text style={styles.bubbleUserText}>{transcript}</Text>
          </View>
        ) : (
          <Text style={styles.hint}>hold the button and talk — turns go through the same chokepoint as everything else</Text>
        )}
        {replyText ? (
          <View style={styles.bubbleAssistant}>
            <Text style={styles.bubbleAssistantText}>{replyText}</Text>
          </View>
        ) : null}
      </ScrollView>

      <View style={styles.dock}>
        <Text style={[styles.statusText, isError && styles.statusError]}>{statusText}</Text>
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
            <Text style={styles.pttIcon}>🎙</Text>
          )}
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.base },
  transcriptArea: { flexGrow: 1, padding: 16, justifyContent: 'flex-end', gap: 12 },
  hint: { color: colors.faint, fontSize: 13, textAlign: 'center', marginTop: 40 },
  bubbleUser: {
    alignSelf: 'flex-end',
    backgroundColor: 'rgba(56,189,248,0.12)',
    borderColor: 'rgba(56,189,248,0.28)',
    borderWidth: 1,
    borderRadius: 16,
    borderTopRightRadius: 4,
    padding: 12,
    maxWidth: '85%',
  },
  bubbleUserText: { color: colors.ink, fontSize: 14 },
  bubbleAssistant: {
    alignSelf: 'flex-start',
    backgroundColor: colors.panel2,
    borderColor: colors.hair,
    borderWidth: 1,
    borderRadius: 16,
    borderTopLeftRadius: 4,
    padding: 12,
    maxWidth: '85%',
  },
  bubbleAssistantText: { color: colors.ink, fontSize: 14 },
  dock: {
    alignItems: 'center',
    paddingVertical: 24,
    borderTopColor: colors.hair,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  statusText: { color: colors.faint, fontSize: 11, marginBottom: 14 },
  statusError: { color: colors.amber },
  pttButton: {
    width: 96,
    height: 96,
    borderRadius: 48,
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
  pttIcon: { fontSize: 38 },
});
