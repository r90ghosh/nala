import { StyleSheet, Text, View } from 'react-native';

import { spacing, typography } from '../lib/theme';

export function SectionHeader({ label }: { label: string }) {
  return (
    <View style={styles.container}>
      <Text style={typography.section}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { paddingHorizontal: spacing.base, paddingTop: spacing.md, paddingBottom: spacing.xs },
});
