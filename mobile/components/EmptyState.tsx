import { Feather } from '@expo/vector-icons';
import type { ComponentProps } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '../lib/theme';

type FeatherName = ComponentProps<typeof Feather>['name'];

export function EmptyState({ icon, title, subtitle }: { icon: FeatherName; title: string; subtitle?: string }) {
  return (
    <View style={styles.container}>
      <Feather name={icon} size={32} color={colors.faint} />
      <Text style={styles.title}>{title}</Text>
      {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: spacing.xl, gap: spacing.sm },
  title: { color: colors.mute, fontSize: 15, fontWeight: '600', textAlign: 'center' },
  subtitle: { color: colors.faint, fontSize: 13, textAlign: 'center', lineHeight: 18 },
});
