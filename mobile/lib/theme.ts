import { Platform, type TextStyle } from 'react-native';

/**
 * Ambient / voice-first palette — near-black glass over a violet→cyan glow
 * ground (mockups/mobile/designs.html, Direction C). Token *names* are kept
 * stable from the prior Mission Control palette so every screen/component
 * that reads `colors.X` re-skins automatically; only the values changed.
 */
export const colors = {
  base: '#06060c',
  panel: '#120f1c',
  panel2: 'rgba(255,255,255,0.07)',
  hair: 'rgba(255,255,255,0.14)',
  ink: '#eaf0fb',
  mute: '#a9b0c6',
  faint: '#6d7288',
  accent: '#a78bfa',
  emerald: '#34d399',
  amber: '#fbbf24',
  red: '#f87171',
  violet: '#a78bfa',
};

/** Violet→cyan accent gradient — primary buttons, the orb, active states. */
export const accentGradient = ['#a78bfa', '#38bdf8'] as const;
/** Dark ink for text/icons placed directly on the accent gradient. */
export const accentOnColor = '#150c2e';

/** The ambient ground: near-black base + soft violet/cyan/pink glows,
 * applied behind every screen (see components/AmbientBackground.tsx). */
export const ground = { top: '#0a0912', bottom: '#06060c' };
export const glows = {
  violetTop: { rgb: '167,139,250', opacity: 0.26 },
  cyanBottomRight: { rgb: '56,189,248', opacity: 0.18 },
  pinkBottomLeft: { rgb: '236,120,190', opacity: 0.1 },
};
/** The orb's core gradient (components/Orb.tsx). */
export const orbStops = ['#d9ccff', '#a78bfa', '#6d4fd6', '#38bdf8'];

/** Feed event type -> color, pastel tints tuned for the glass/dark ground
 * (was matching the web Mission Control's app.js exactly; kept the same
 * semantic mapping, lightened for contrast against the ambient background). */
export const TYPE_COLORS: Record<string, string> = {
  signal: '#7dd3fc',
  triage: '#c4b5fd',
  utterance: '#7dd3fc',
  llm_request: '#c4b5fd',
  llm_response: '#c4b5fd',
  tool_call: '#6ee7b7',
  tool_result: '#6ee7b7',
  memory_write: '#fcd34d',
  rejected: '#fcd34d',
  error: '#fca5a5',
  briefing: '#aab2c6',
  stt_result: '#aab2c6',
  tts_result: '#aab2c6',
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
  xl: 20,
  xxl: 24,
  pill: 999,
};

// React Native doesn't ship JetBrains Mono the way the web client loads it
// from Google Fonts — bundling a custom font is more infra than this pass
// needs, so token/id text uses the platform's built-in monospace face.
const monoFontFamily = Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' });

export const typography: Record<string, TextStyle> = {
  display: { fontSize: 30, fontWeight: '700', color: colors.ink },
  title: { fontSize: 20, fontWeight: '700', color: colors.ink },
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
