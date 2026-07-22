import { useCallback, useEffect, useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { apiGet, apiPost } from '../../lib/api';
import { colors, STATUS_COLORS } from '../../lib/theme';
import type { ProcessedAction } from '../../lib/types';

const POLL_MS = 4000;

function ProvenanceBlock({ action }: { action: ProcessedAction }) {
  const origin = action.origin;
  if (!origin || origin.kind !== 'proactive') {
    return (
      <View style={[styles.provenance, styles.provenanceUser]}>
        <Text style={styles.provenanceLabel}>USER-INITIATED</Text>
        <Text style={styles.provenanceText}>requested directly by the operator</Text>
      </View>
    );
  }
  return (
    <View style={[styles.provenance, styles.provenanceProactive]}>
      <Text style={[styles.provenanceLabel, { color: colors.violet }]}>PROACTIVE PROPOSAL</Text>
      <Text style={styles.provenanceText}>
        proposed by {origin.model || 'unknown model'} · from {origin.source || 'unknown source'}:{' '}
        {origin.signal_title || '(no title)'} · reason: {origin.reason || '(no reason given)'}
      </Text>
    </View>
  );
}

function ActionCard({
  action,
  onResolve,
}: {
  action: ProcessedAction;
  onResolve: (token: string, verb: 'confirm' | 'reject') => void;
}) {
  const token = action.idempotency_key.slice(0, 8);
  const canResolve = action.status === 'awaiting_confirm';
  return (
    <View style={styles.card}>
      <View style={styles.cardTop}>
        <Text style={styles.cardTitle} numberOfLines={2}>
          {action.action_type} {action.args_json}
        </Text>
        <View style={[styles.badge, { backgroundColor: `${STATUS_COLORS[action.status] || colors.faint}22` }]}>
          <Text style={[styles.badgeText, { color: STATUS_COLORS[action.status] || colors.faint }]}>
            {action.status}
          </Text>
        </View>
      </View>
      {canResolve ? <ProvenanceBlock action={action} /> : null}
      <Text style={styles.meta}>{action.created_at}</Text>
      {canResolve ? (
        <View style={styles.actionsRow}>
          <Pressable style={[styles.actionBtn, styles.confirmBtn]} onPress={() => onResolve(token, 'confirm')}>
            <Text style={[styles.actionBtnText, { color: colors.emerald }]}>Confirm</Text>
          </Pressable>
          <Pressable style={[styles.actionBtn, styles.rejectBtn]} onPress={() => onResolve(token, 'reject')}>
            <Text style={[styles.actionBtnText, { color: colors.red }]}>Reject</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

export default function ActionsScreen() {
  const [actions, setActions] = useState<ProcessedAction[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await apiGet<ProcessedAction[]>('/api/actions');
      setActions(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'actions unreachable');
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  async function handleResolve(token: string, verb: 'confirm' | 'reject') {
    try {
      await apiPost(`/api/actions/${encodeURIComponent(token)}/${verb}`);
    } finally {
      load();
    }
  }

  async function onRefresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }

  const awaiting = actions.filter((a) => a.status === 'awaiting_confirm');
  const recent = actions.filter((a) => a.status !== 'awaiting_confirm').slice(0, 20);
  const sections = [...awaiting, ...recent];

  return (
    <View style={styles.container}>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <FlatList
        data={sections}
        keyExtractor={(item) => item.idempotency_key}
        contentContainerStyle={sections.length === 0 ? styles.emptyContainer : styles.listContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}
        ListEmptyComponent={<Text style={styles.empty}>nothing awaiting confirmation</Text>}
        renderItem={({ item }) => <ActionCard action={item} onResolve={handleResolve} />}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.base },
  listContent: { padding: 12 },
  card: {
    backgroundColor: colors.panel2,
    borderColor: colors.hair,
    borderWidth: 1,
    borderRadius: 10,
    padding: 12,
    marginBottom: 10,
  },
  cardTop: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  cardTitle: { color: colors.ink, fontSize: 13, flex: 1, lineHeight: 18 },
  badge: { borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 },
  badgeText: { fontSize: 9, fontWeight: '700' },
  provenance: { marginTop: 8, padding: 8, borderRadius: 7 },
  provenanceUser: { backgroundColor: 'rgba(255,255,255,0.03)', borderColor: colors.hair, borderWidth: 1 },
  provenanceProactive: { backgroundColor: 'rgba(167,139,250,0.08)', borderColor: 'rgba(167,139,250,0.35)', borderWidth: 1 },
  provenanceLabel: { fontSize: 9, fontWeight: '700', color: colors.faint, marginBottom: 3, letterSpacing: 0.5 },
  provenanceText: { fontSize: 11, color: colors.mute, lineHeight: 15 },
  meta: { color: colors.faint, fontSize: 10, marginTop: 6 },
  actionsRow: { flexDirection: 'row', gap: 8, marginTop: 10 },
  actionBtn: { flex: 1, borderRadius: 7, paddingVertical: 10, alignItems: 'center', borderWidth: 1 },
  confirmBtn: { backgroundColor: 'rgba(52,211,153,0.14)', borderColor: 'rgba(52,211,153,0.35)' },
  rejectBtn: { backgroundColor: 'rgba(248,113,113,0.12)', borderColor: 'rgba(248,113,113,0.3)' },
  actionBtnText: { fontWeight: '700', fontSize: 13 },
  empty: { color: colors.faint, textAlign: 'center', fontSize: 13 },
  emptyContainer: { flex: 1, justifyContent: 'center' },
  error: { color: colors.red, padding: 10, fontSize: 12, textAlign: 'center' },
});
