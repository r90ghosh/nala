import { useCallback, useEffect, useState } from 'react';
import { FlatList, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { apiGet } from '../../lib/api';
import { colors } from '../../lib/theme';
import type { MemoryGraph, MemoryNode } from '../../lib/types';

const KIND_COLORS: Record<string, string> = {
  person: '#f472b6',
  project: colors.accent,
  preference: colors.violet,
  event: colors.amber,
  thing: colors.emerald,
  place: '#22d3ee',
};

function NodeRow({ node, factCount }: { node: MemoryNode; factCount: number }) {
  const color = KIND_COLORS[node.kind] || colors.faint;
  return (
    <View style={styles.row}>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <View style={styles.rowBody}>
        <Text style={styles.label}>{node.label}</Text>
        <Text style={styles.meta}>
          {node.kind} · {node.purpose_scope} · {factCount} observation{factCount === 1 ? '' : 's'}
        </Text>
      </View>
    </View>
  );
}

export default function MemoryScreen() {
  const [graph, setGraph] = useState<MemoryGraph>({ nodes: [], edges: [], observations: [] });
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await apiGet<MemoryGraph>('/api/memory');
      setGraph(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'memory unreachable');
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

  const factCountByNode: Record<string, number> = {};
  for (const obs of graph.observations) {
    factCountByNode[obs.node_id] = (factCountByNode[obs.node_id] || 0) + 1;
  }

  return (
    <View style={styles.container}>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <FlatList
        data={graph.nodes}
        keyExtractor={(item) => item.node_id}
        contentContainerStyle={graph.nodes.length === 0 ? styles.emptyContainer : styles.listContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}
        ListEmptyComponent={
          <Text style={styles.empty}>
            no memory yet — run `python -m nala.seed_memory` on the Mac, or tell chat something to remember
          </Text>
        }
        renderItem={({ item }) => <NodeRow node={item} factCount={factCountByNode[item.node_id] || 0} />}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.base },
  listContent: { padding: 12 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: colors.panel2,
    borderColor: colors.hair,
    borderWidth: 1,
    borderRadius: 9,
    padding: 12,
    marginBottom: 8,
  },
  dot: { width: 10, height: 10, borderRadius: 5, flexShrink: 0 },
  rowBody: { flex: 1 },
  label: { color: colors.ink, fontSize: 14, fontWeight: '600' },
  meta: { color: colors.faint, fontSize: 11, marginTop: 2 },
  empty: { color: colors.faint, textAlign: 'center', fontSize: 13, paddingHorizontal: 24, lineHeight: 19 },
  emptyContainer: { flex: 1, justifyContent: 'center' },
  error: { color: colors.red, padding: 10, fontSize: 12, textAlign: 'center' },
});
