import { Feather } from '@expo/vector-icons';
import { useCallback, useEffect, useState } from 'react';
import { FlatList, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { Badge } from '../../components/Badge';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { EmptyState } from '../../components/EmptyState';
import { Screen } from '../../components/Screen';
import { SectionHeader } from '../../components/SectionHeader';
import { ServerUnreachableBanner } from '../../components/ServerUnreachableBanner';
import { apiGet, apiPost } from '../../lib/api';
import { colors, radii, spacing, typography, STATUS_COLORS } from '../../lib/theme';
import type { ProcessedAction } from '../../lib/types';

const POLL_MS = 4000;

function ProvenanceBlock({ action }: { action: ProcessedAction }) {
  const origin = action.origin;
  if (!origin || origin.kind !== 'proactive') {
    return (
      <View style={[styles.provenance, styles.provenanceUser]}>
        <View style={styles.provenanceLabelRow}>
          <Feather name="user" size={11} color={colors.faint} />
          <Text style={styles.provenanceLabel}>User-initiated</Text>
        </View>
        <Text style={styles.provenanceText}>Requested directly by you.</Text>
      </View>
    );
  }
  return (
    <View style={[styles.provenance, styles.provenanceProactive]}>
      <View style={styles.provenanceLabelRow}>
        <Feather name="zap" size={11} color={colors.violet} />
        <Text style={[styles.provenanceLabel, { color: colors.violet }]}>Proactive proposal</Text>
      </View>
      <Text style={styles.provenanceText}>
        Proposed by {origin.model || 'unknown model'}, from {origin.source || 'unknown source'}:{' '}
        {origin.signal_title || '(no title)'}. Reason: {origin.reason || '(no reason given)'}
      </Text>
    </View>
  );
}

function ActionCard({
  action,
  resolving,
  onResolve,
}: {
  action: ProcessedAction;
  resolving: boolean;
  onResolve: (token: string, verb: 'confirm' | 'reject') => void;
}) {
  const token = action.idempotency_key.slice(0, 8);
  const canResolve = action.status === 'awaiting_confirm';
  return (
    <Card style={styles.card}>
      <View style={styles.cardTop}>
        <Text style={styles.cardTitle} numberOfLines={2}>
          {action.action_type} {action.args_json}
        </Text>
        <Badge label={action.status.replace(/_/g, ' ')} color={STATUS_COLORS[action.status] || colors.faint} />
      </View>
      {canResolve ? <ProvenanceBlock action={action} /> : null}
      {canResolve ? (
        <View style={styles.actionsRow}>
          <Button
            label="Confirm"
            variant="primary"
            loading={resolving}
            onPress={() => onResolve(token, 'confirm')}
            style={styles.actionBtn}
          />
          <Button
            label="Reject"
            variant="ghost"
            disabled={resolving}
            onPress={() => onResolve(token, 'reject')}
            style={styles.actionBtn}
          />
        </View>
      ) : (
        <Text style={styles.meta}>{action.created_at}</Text>
      )}
    </Card>
  );
}

export default function ActionsScreen() {
  const [actions, setActions] = useState<ProcessedAction[]>([]);
  const [unreachable, setUnreachable] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [resolvingToken, setResolvingToken] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await apiGet<ProcessedAction[]>('/api/actions');
      setActions(data);
      setUnreachable(false);
    } catch {
      setUnreachable(true);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  async function handleResolve(token: string, verb: 'confirm' | 'reject') {
    setResolvingToken(token);
    try {
      await apiPost(`/api/actions/${encodeURIComponent(token)}/${verb}`);
      // Optimistic removal — don't make the user wait for the next poll to
      // see the card they just resolved disappear.
      setActions((prev) => prev.filter((a) => !a.idempotency_key.startsWith(token)));
    } finally {
      setResolvingToken(null);
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

  type Row = { kind: 'header'; label: string } | { kind: 'action'; action: ProcessedAction };
  const rows: Row[] = [
    ...(awaiting.length ? [{ kind: 'header' as const, label: 'Awaiting confirmation' }] : []),
    ...awaiting.map((action) => ({ kind: 'action' as const, action })),
    ...(recent.length ? [{ kind: 'header' as const, label: 'Recent' }] : []),
    ...recent.map((action) => ({ kind: 'action' as const, action })),
  ];

  return (
    <Screen title="Actions">
      {unreachable ? <ServerUnreachableBanner /> : null}
      <FlatList
        data={rows}
        keyExtractor={(item) => (item.kind === 'header' ? `h-${item.label}` : item.action.idempotency_key)}
        contentContainerStyle={rows.length === 0 ? styles.emptyContainer : styles.listContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}
        ListEmptyComponent={
          <EmptyState icon="check-circle" title="Nothing needs your confirmation." subtitle="Proposed actions will show up here." />
        }
        renderItem={({ item }) =>
          item.kind === 'header' ? (
            <SectionHeader label={item.label} />
          ) : (
            <ActionCard
              action={item.action}
              resolving={resolvingToken === item.action.idempotency_key.slice(0, 8)}
              onResolve={handleResolve}
            />
          )
        }
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  listContent: { padding: spacing.base },
  emptyContainer: { flex: 1 },
  card: { marginBottom: spacing.sm, gap: spacing.sm },
  cardTop: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.sm },
  cardTitle: { ...typography.body, fontSize: 14, flex: 1, lineHeight: 19 },
  provenance: { padding: spacing.sm, borderRadius: radii.sm, gap: 4 },
  provenanceUser: { backgroundColor: 'rgba(255,255,255,0.03)', borderColor: colors.hair, borderWidth: 1 },
  provenanceProactive: { backgroundColor: 'rgba(167,139,250,0.08)', borderColor: 'rgba(167,139,250,0.35)', borderWidth: 1 },
  provenanceLabelRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  provenanceLabel: { fontSize: 10, fontWeight: '700', color: colors.faint, letterSpacing: 0.4 },
  provenanceText: { fontSize: 12, color: colors.mute, lineHeight: 16 },
  meta: { ...typography.caption },
  actionsRow: { flexDirection: 'row', gap: spacing.sm },
  actionBtn: { flex: 1 },
});
