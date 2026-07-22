import type { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, spacing, typography } from '../lib/theme';

type ScreenProps = {
  title?: string;
  headerRight?: ReactNode;
  children: ReactNode;
};

/** Every screen's outer shell: safe-area top inset + an optional header row.
 * Bottom inset is left to the tab bar itself (React Navigation already
 * accounts for it), so screen content can flow naturally above it. */
export function Screen({ title, headerRight, children }: ScreenProps) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {title ? (
        <View style={styles.header}>
          <Text style={typography.title}>{title}</Text>
          {headerRight}
        </View>
      ) : null}
      <View style={styles.body}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.base },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.md,
    borderBottomColor: colors.hair,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  body: { flex: 1 },
});
