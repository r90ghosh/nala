import { Feather } from '@expo/vector-icons';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Modal, Pressable, RefreshControl, ScrollView, SectionList, StyleSheet, Text, View } from 'react-native';

import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { Chip } from '../../components/Chip';
import { EmptyState } from '../../components/EmptyState';
import { Screen } from '../../components/Screen';
import { SectionHeader } from '../../components/SectionHeader';
import { ServerUnreachableBanner } from '../../components/ServerUnreachableBanner';
import { apiGet } from '../../lib/api';
import { usePairingContext } from '../../lib/PairingContext';
import { clearPairing, getPairing } from '../../lib/pairing';
import { colors, radii, spacing, typography, TYPE_COLORS } from '../../lib/theme';
import type { FeedEvent } from '../../lib/types';

const POLL_MS = 3000;
const MAX_ROWS = 200;

const TYPE_LABELS: Record<string, string> = {
  signal: 'Signal',
  triage: 'Triage',
  utterance: 'You said',
  llm_request: 'Thinking',
  llm_response: 'Decided',
  tool_call: 'Tool call',
  tool_result: 'Tool result',
  memory_write: 'Memory',
  rejected: 'Rejected',
  error: 'Error',
  briefing: 'Briefing',
  stt_result: 'Heard',
  tts_result: 'Spoke',
};

function humanType(type: string): string {
  return TYPE_LABELS[type] || type;
}

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

function relativeTime(ts: string): string {
  const diffSec = Math.max(0, Math.floor((Date.now() - new Date(ts).getTime()) / 1000));
  if (diffSec < 60) return 'just now';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${Math.floor(diffHr / 24)}d ago`;
}

function timeBucket(ts: string): string {
  const then = new Date(ts);
  const now = new Date();
  const diffMin = (now.getTime() - then.getTime()) / 60000;
  if (diffMin < 5) return 'Just now';
  if (then.toDateString() === now.toDateString()) return 'Earlier today';
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (then.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return then.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function groupIntoSections(rows: FeedEvent[]): { title: string; data: FeedEvent[] }[] {
  const sections: { title: string; data: FeedEvent[] }[] = [];
  for (const row of rows) {
    const bucket = timeBucket(row.ts);
    const last = sections[sections.length - 1];
    if (last && last.title === bucket) {
      last.data.push(row);
    } else {
      sections.push({ title: bucket, data: [row] });
    }
  }
  return sections;
}

export default function FeedScreen() {
  const [rows, setRows] = useState<FeedEvent[]>([]);
  const [unreachable, setUnreachable] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [selected, setSelected] = useState<FeedEvent | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [serverUrl, setServerUrl] = useState('');
  const { markUnpaired } = usePairingContext();
  const lastIdRef = useRef(0);

  const poll = useCallback(async () => {
    try {
      const newRows = await apiGet<FeedEvent[]>(`/api/events?since=${lastIdRef.current}`);
      if (newRows.length) {
        lastIdRef.current = Math.max(lastIdRef.current, ...newRows.map((r) => r.id));
        // The web UI's own 60s /api/status cache-refresh runs report_status
        // through the chokepoint too — still logged (nothing is ever
        // off-log), just excluded here so routine polling doesn't drown out
        // real activity, matching nala/static/app.js's own filter.
        const visible = newRows.filter((r) => {
          try {
            return JSON.parse(r.payload_json).actor !== 'status-cache';
          } catch {
            return true;
          }
        });
        if (visible.length) {
          setRows((prev) => [...visible.slice().reverse(), ...prev].slice(0, MAX_ROWS));
        }
      }
      setUnreachable(false);
    } catch {
      setUnreachable(true);
    }
  }, []);

  useEffect(() => {
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => clearInterval(id);
  }, [poll]);

  async function onRefresh() {
    setRefreshing(true);
    await poll();
    setRefreshing(false);
  }

  async function openSettings() {
    const pairing = await getPairing();
    setServerUrl(pairing?.serverUrl || '');
    setSettingsOpen(true);
  }

  async function handleUnpair() {
    await clearPairing();
    setSettingsOpen(false);
    markUnpaired();
  }

  const sections = groupIntoSections(rows);

  return (
    <Screen
      title="Feed"
      headerRight={
        <Pressable onPress={openSettings} hitSlop={12}>
          <Feather name="settings" size={20} color={colors.mute} />
        </Pressable>
      }
    >
      {unreachable ? <ServerUnreachableBanner /> : null}
      <SectionList
        sections={sections}
        keyExtractor={(item) => String(item.id)}
        stickySectionHeadersEnabled
        contentContainerStyle={sections.length === 0 ? styles.emptyContainer : styles.listContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}
        ListEmptyComponent={
          <EmptyState
            icon="activity"
            title="No activity yet"
            subtitle="Nala is watching your inbox, calendar, and repos — activity will show up here."
          />
        }
        renderSectionHeader={({ section }) => <SectionHeader label={section.title} />}
        renderItem={({ item }) => {
          const color = TYPE_COLORS[item.type] || colors.faint;
          return (
            <Pressable onPress={() => setSelected(item)}>
              <Card style={styles.card}>
                <View style={styles.cardTop}>
                  <View style={styles.typeRow}>
                    <View style={[styles.dot, { backgroundColor: color }]} />
                    <Chip label={humanType(item.type)} color={color} />
                  </View>
                  <Text style={styles.time}>{relativeTime(item.ts)}</Text>
                </View>
                <Text style={styles.summary} numberOfLines={2}>
                  {summarize(item)}
                </Text>
              </Card>
            </Pressable>
          );
        }}
      />

      <Modal visible={!!selected} animationType="slide" transparent onRequestClose={() => setSelected(null)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHeader}>
              <Text style={typography.title}>{selected ? humanType(selected.type) : ''}</Text>
              <Pressable onPress={() => setSelected(null)} hitSlop={12}>
                <Feather name="x" size={22} color={colors.mute} />
              </Pressable>
            </View>
            <ScrollView style={styles.modalBody}>
              <Text style={[typography.mono, styles.modalJson]}>
                {selected ? JSON.stringify(JSON.parse(selected.payload_json || '{}'), null, 2) : ''}
              </Text>
            </ScrollView>
          </View>
        </View>
      </Modal>

      <Modal visible={settingsOpen} animationType="slide" transparent onRequestClose={() => setSettingsOpen(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHeader}>
              <Text style={typography.title}>Settings</Text>
              <Pressable onPress={() => setSettingsOpen(false)} hitSlop={12}>
                <Feather name="x" size={22} color={colors.mute} />
              </Pressable>
            </View>
            <View style={styles.modalBody}>
              <Text style={typography.section}>Paired server</Text>
              <Text style={[typography.mono, styles.serverUrlText]}>{serverUrl || '—'}</Text>
              <Button label="Unpair" variant="danger" onPress={handleUnpair} style={{ marginTop: spacing.xl }} />
            </View>
          </View>
        </View>
      </Modal>
    </Screen>
  );
}

const styles = StyleSheet.create({
  listContent: { padding: spacing.base, gap: spacing.sm },
  emptyContainer: { flex: 1 },
  card: { marginBottom: spacing.sm, gap: spacing.xs },
  cardTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  typeRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  dot: { width: 8, height: 8, borderRadius: 4 },
  time: { ...typography.caption },
  summary: { ...typography.body, lineHeight: 20 },
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
  modalJson: { lineHeight: 18 },
  serverUrlText: { marginTop: spacing.xs },
});
