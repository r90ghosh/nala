/** Mirrors nala/serve.py's JSON response shapes exactly — see that file for
 * the authoritative contract. */

export type FeedEvent = {
  id: number;
  ts: string;
  session_id: string;
  turn_id: string | null;
  type: string;
  level: string;
  payload_json: string;
};

export type ActionOrigin = {
  kind: 'user' | 'proactive';
  source?: string;
  signal_title?: string;
  model?: string;
  reason?: string;
};

export type ProcessedAction = {
  idempotency_key: string;
  turn_id: string;
  action_type: string;
  reversibility: string;
  args_json: string;
  status: string;
  result_json: string | null;
  error_json: string | null;
  created_at: string;
  resolved_at: string | null;
  origin?: ActionOrigin;
};

export type VoiceTurnDone = {
  turn_id: string;
  transcript: string;
  reply_text: string;
  status: string;
  confirm_token: string | null;
  events: FeedEvent[];
  audio_b64: string;
};

export type VoiceTurnAskRepeat = {
  ask_repeat: true;
  reason: string;
  turn_id: string;
  transcript: string;
};

export type VoiceTurnResponse = VoiceTurnDone | VoiceTurnAskRepeat;

/** Response shape of POST /api/turn — the typed-text counterpart to
 * /api/voice/turn, minus the transcript/audio fields (see serve.py). */
export type TextTurnResponse = {
  turn_id: string;
  reply_text: string;
  status: string;
  confirm_token: string | null;
  events: FeedEvent[];
};

export function isAskRepeat(r: VoiceTurnResponse): r is VoiceTurnAskRepeat {
  return 'ask_repeat' in r && r.ask_repeat === true;
}

export type MemoryNode = {
  node_id: string;
  kind: string;
  label: string;
  purpose_scope: string;
  created_at: string;
  updated_at: string;
};

export type MemoryEdge = {
  edge_id: string;
  src_node: string;
  rel: string;
  dst_node: string;
  created_at: string;
};

export type MemoryObservation = {
  obs_id: string;
  node_id: string;
  fact: string;
  source: string;
  source_ref: string;
  observed_at: string;
  created_at: string;
};

export type MemoryGraph = {
  nodes: MemoryNode[];
  edges: MemoryEdge[];
  observations: MemoryObservation[];
};

export type PurposeInfo = {
  name: string;
  display_name: string;
  risk_profile: string;
};
