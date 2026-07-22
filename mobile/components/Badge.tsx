import { StyleSheet, Text, View } from 'react-native';

import { radii, spacing } from '../lib/theme';

/** Filled, bolder-weight status pill — action/processed-action status. */
export function Badge({ label, color }: { label: string; color: string }) {
  return (
    <View style={[styles.badge, { backgroundColor: `${color}26` }]}>
      <Text style={[styles.text, { color }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    borderRadius: radii.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    alignSelf: 'flex-start',
  },
  text: { fontSize: 10, fontWeight: '700' },
});
