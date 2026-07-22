import { useCallback, useEffect, useRef, useState } from 'react';
import { FlatList, StyleSheet, Text, View } from 'react-native';

import { apiGet } from '../../lib/api';
import { colors, TYPE_COLORS } from '../../lib/theme';
import type { FeedEvent } from '../../lib/types';

const POLL_MS = 3000;
const MAX_ROWS = 200;

function summarize(row: FeedEvent): string {
  let payload: Record<string, unknown> = {};
  try {
    payload = JSON.parse(row.payload_json);
  } catch {
    return row.payload_json;
  }
  switch (row.type) {
    case 'signal':
      return `${payload.source}: ${payload.title}`;
    case 'triage':
      if (payload.classification) return `${payload.classification} — ${payload.reason || ''}`;
      if (payload.rejected) return `rejected — ${payload.reason || ''}`;
      return JSON.stringify(payload);
    case 'tool_call':
      return `${payload.action_type} ${JSON.stringify(payload.args || {})}`;
    case 'tool_result':
      return `${payload.action_type} → result`;
    case 'utterance':
      return `"${payload.text}"`;
    case 'llm_request':
      return `${payload.model || ''}: ${String(payload.utterance || '').slice(0, 60)}`;
    case 'llm_response':
      return `tool=${payload.tool_name || 'none'}`;
    case 'error':
      return `${payload.context || ''}: ${payload.message || ''}`;
    case 'rejected':
      return String(payload.reason || JSON.stringify(payload));
    default:
      return JSON.stringify(payload);
  }
}

export default function FeedScreen() {
  const [rows, setRows] = useState<FeedEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const lastIdRef = useRef(0);

  const poll = useCallback(async () => {
    try {
      const newRows = await apiGet<FeedEvent[]>(`/api/events?since=${lastIdRef.current}`);
      if (newRows.length) {
        lastIdRef.current = Math.max(lastIdRef.current, ...newRows.map((r) => r.id));
        setRows((prev) => [...newRows.slice().reverse(), ...prev].slice(0, MAX_ROWS));
      }
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'feed unreachable');
    }
  }, []);

  useEffect(() => {
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => clearInterval(id);
  }, [poll]);

  return (
    <View style={styles.container}>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <FlatList
        data={rows}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={rows.length === 0 ? styles.emptyContainer : undefined}
        ListEmptyComponent={<Text style={styles.empty}>no events yet</Text>}
        renderItem={({ item }) => {
          const color = TYPE_COLORS[item.type] || colors.faint;
          return (
            <View style={styles.row}>
              <Text style={styles.time}>{item.ts.slice(11, 19)}</Text>
              <View style={[styles.typeChip, { backgroundColor: `${color}22`, borderColor: `${color}55` }]}>
                <Text style={[styles.typeText, { color }]}>{item.type}</Text>
              </View>
              <Text style={styles.payload} numberOfLines={2}>
                {summarize(item)}
              </Text>
            </View>
          );
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.base },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderBottomColor: colors.hair,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  time: { color: colors.faint, fontSize: 10, width: 56 },
  typeChip: { borderWidth: 1, borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 },
  typeText: { fontSize: 9, fontWeight: '600' },
  payload: { color: colors.ink, fontSize: 12, flex: 1 },
  empty: { color: colors.faint, textAlign: 'center', fontSize: 13 },
  emptyContainer: { flex: 1, justifyContent: 'center' },
  error: { color: colors.red, padding: 10, fontSize: 12, textAlign: 'center' },
});
