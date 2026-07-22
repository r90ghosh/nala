import { Platform, type TextStyle } from 'react-native';

/**
 * Shared color palette — matches the web Mission Control's :root variables
 * (nala/static/style.css) so the iOS app doesn't invent a second visual
 * language for the same product.
 */
export const colors = {
  base: '#0a0e14',
  panel: '#0f131b',
  panel2: '#111827',
  hair: '#1e2430',
  ink: '#e5edf5',
  mute: '#8a97a8',
  faint: '#5a6678',
  accent: '#38bdf8',
  emerald: '#34d399',
  amber: '#fbbf24',
  red: '#f87171',
  violet: '#a78bfa',
};

/** Feed event type -> color, matching app.js's TYPE_COLORS exactly. */
export const TYPE_COLORS: Record<string, string> = {
  signal: '#22d3ee',
  triage: '#94a3b8',
  utterance: '#38bdf8',
  llm_request: '#a78bfa',
  llm_response: '#a78bfa',
  tool_call: '#fbbf24',
  tool_result: '#34d399',
  memory_write: '#a78bfa',
  rejected: '#fbbf24',
  error: '#f87171',
  briefing: '#94a3b8',
  stt_result: '#94a3b8',
  tts_result: '#94a3b8',
};

/** Purpose risk_profile -> badge color, matching the web purpose rail. */
export const RISK_COLORS: Record<string, string> = {
  act_confirm: colors.amber,
  notify_only: colors.violet,
  read_only: colors.faint,
};

export const STATUS_COLORS: Record<string, string> = {
  awaiting_confirm: colors.amber,
  notified: colors.violet,
  done: colors.emerald,
  failed: colors.red,
  rejected: colors.faint,
  dismissed: colors.faint,
  pending: colors.amber,
};

/** 4/8/12/16/20/24/32 spacing scale — every screen should size gaps and
 * padding from this, not a one-off number. */
export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  base: 16,
  lg: 20,
  xl: 24,
  xxl: 32,
};

export const radii = {
  sm: 8,
  md: 12,
  lg: 16,
  pill: 999,
};

// React Native doesn't ship JetBrains Mono the way the web client loads it
// from Google Fonts — bundling a custom font is more infra than this pass
// needs, so token/id text uses the platform's built-in monospace face.
const monoFontFamily = Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' });

export const typography: Record<string, TextStyle> = {
  display: { fontSize: 30, fontWeight: '700', color: '#fff' },
  title: { fontSize: 20, fontWeight: '700', color: '#fff' },
  section: {
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 1,
    color: colors.faint,
  },
  body: { fontSize: 15, fontWeight: '400', color: colors.ink },
  caption: { fontSize: 12, fontWeight: '400', color: colors.faint },
  mono: { fontFamily: monoFontFamily, fontSize: 13, color: colors.ink },
};
