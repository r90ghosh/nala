import { Feather } from '@expo/vector-icons';
import type { ComponentProps } from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Modal, Pressable, RefreshControl, ScrollView, SectionList, StyleSheet, Text, TextInput, View } from 'react-native';

import { Card } from '../../components/Card';
import { EmptyState } from '../../components/EmptyState';
import { Screen } from '../../components/Screen';
import { SectionHeader } from '../../components/SectionHeader';
import { ServerUnreachableBanner } from '../../components/ServerUnreachableBanner';
import { apiGet } from '../../lib/api';
import { colors, radii, spacing, typography } from '../../lib/theme';
import type { MemoryGraph, MemoryNode, MemoryObservation } from '../../lib/types';

type FeatherName = ComponentProps<typeof Feather>['name'];

const KIND_COLORS: Record<string, string> = {
  person: '#f472b6',
  project: colors.accent,
  preference: colors.violet,
  event: colors.amber,
  thing: colors.emerald,
  place: '#22d3ee',
};

const KIND_ICONS: Record<string, FeatherName> = {
  person: 'user',
  project: 'folder',
  preference: 'heart',
  event: 'calendar',
  thing: 'box',
  place: 'map-pin',
};

function formatProvenanceChip(source: string, observedAt: string): string {
  const d = new Date(observedAt);
  const label = source === 'user_said' ? 'you said' : source;
  const dateStr = Number.isNaN(d.getTime()) ? '' : `${d.getMonth() + 1}/${d.getDate()}`;
  return dateStr ? `${label} ${dateStr}` : label;
}

export default function MemoryScreen() {
  const [graph, setGraph] = useState<MemoryGraph>({ nodes: [], edges: [], observations: [] });
  const [unreachable, setUnreachable] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<MemoryNode | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await apiGet<MemoryGraph>('/api/memory');
      setGraph(data);
      setUnreachable(false);
    } catch {
      setUnreachable(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function onRefresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }

  const factCountByNode = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const obs of graph.observations) counts[obs.node_id] = (counts[obs.node_id] || 0) + 1;
    return counts;
  }, [graph.observations]);

  const sections = useMemo(() => {
    const filtered = query.trim()
      ? graph.nodes.filter((n) => n.label.toLowerCase().includes(query.trim().toLowerCase()))
      : graph.nodes;

    const byScope = new Map<string, MemoryNode[]>();
    for (const node of filtered) {
      const list = byScope.get(node.purpose_scope) || [];
      list.push(node);
      byScope.set(node.purpose_scope, list);
    }
    return Array.from(byScope.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([scope, nodes]) => ({ title: scope, data: nodes }));
  }, [graph.nodes, query]);

  const selectedObservations: MemoryObservation[] = selected
    ? graph.observations.filter((o) => o.node_id === selected.node_id)
    : [];

  return (
    <Screen title="Memory">
      {unreachable ? <ServerUnreachableBanner /> : null}
      <View style={styles.searchWrap}>
        <Feather name="search" size={16} color={colors.faint} />
        <TextInput
          style={styles.searchInput}
          value={query}
          onChangeText={setQuery}
          placeholder="Search memory…"
          placeholderTextColor={colors.faint}
          autoCapitalize="none"
          autoCorrect={false}
        />
      </View>

      <SectionList
        sections={sections}
        keyExtractor={(item) => item.node_id}
        stickySectionHeadersEnabled
        contentContainerStyle={sections.length === 0 ? styles.emptyContainer : styles.listContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}
        ListEmptyComponent={
          <EmptyState
            icon="cpu"
            title="No memory yet"
            subtitle="Run `python -m nala.seed_memory` on the Mac, or tell chat something to remember."
          />
        }
        renderSectionHeader={({ section }) => <SectionHeader label={section.title} />}
        renderItem={({ item }) => {
          const color = KIND_COLORS[item.kind] || colors.faint;
          const factCount = factCountByNode[item.node_id] || 0;
          return (
            <Pressable onPress={() => setSelected(item)}>
              <Card style={styles.card}>
                <View style={[styles.iconWrap, { backgroundColor: `${color}22`, borderColor: `${color}55` }]}>
                  <Feather name={KIND_ICONS[item.kind] || 'circle'} size={16} color={color} />
                </View>
                <View style={styles.cardBody}>
                  <Text style={styles.label}>{item.label}</Text>
                  <Text style={styles.caption}>
                    {item.kind} · {factCount} observation{factCount === 1 ? '' : 's'}
                  </Text>
                </View>
                <Feather name="chevron-right" size={18} color={colors.faint} />
              </Card>
            </Pressable>
          );
        }}
      />

      <Modal visible={!!selected} animationType="slide" transparent onRequestClose={() => setSelected(null)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHeader}>
              <Text style={typography.title}>{selected?.label}</Text>
              <Pressable onPress={() => setSelected(null)} hitSlop={12}>
                <Feather name="x" size={22} color={colors.mute} />
              </Pressable>
            </View>
            <ScrollView style={styles.modalBody}>
              {selectedObservations.length === 0 ? (
                <Text style={styles.caption}>No observations recorded yet.</Text>
              ) : (
                selectedObservations.map((obs) => (
                  <View key={obs.obs_id} style={styles.obsRow}>
                    <Text style={styles.obsFact}>{obs.fact}</Text>
                    <View style={styles.provChip}>
                      <Text style={styles.provChipText}>{formatProvenanceChip(obs.source, obs.observed_at)}</Text>
                    </View>
                  </View>
                ))
              )}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </Screen>
  );
}

const styles = StyleSheet.create({
  searchWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.panel2,
    borderColor: colors.hair,
    borderWidth: 1,
    borderRadius: radii.md,
    marginHorizontal: spacing.base,
    marginTop: spacing.sm,
    paddingHorizontal: spacing.md,
    minHeight: 42,
  },
  searchInput: { flex: 1, color: colors.ink, fontSize: 14, paddingVertical: spacing.sm },
  listContent: { padding: spacing.base },
  emptyContainer: { flex: 1 },
  card: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, marginBottom: spacing.sm },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: radii.sm,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardBody: { flex: 1 },
  label: { ...typography.body, fontWeight: '600' },
  caption: { ...typography.caption, marginTop: 2 },
  modalBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  modalSheet: {
    backgroundColor: colors.panel,
    borderTopLeftRadius: radii.lg,
    borderTopRightRadius: radii.lg,
    maxHeight: '75%',
    paddingBottom: spacing.xl,
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: spacing.base,
    borderBottomColor: colors.hair,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  modalBody: { padding: spacing.base },
  obsRow: {
    backgroundColor: colors.panel2,
    borderColor: colors.hair,
    borderWidth: 1,
    borderRadius: radii.sm,
    padding: spacing.md,
    marginBottom: spacing.sm,
    gap: spacing.xs,
  },
  obsFact: { ...typography.body, lineHeight: 20 },
  provChip: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(167,139,250,0.1)',
    borderColor: 'rgba(167,139,250,0.28)',
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  provChipText: { color: colors.violet, fontSize: 10, fontWeight: '600' },
});
