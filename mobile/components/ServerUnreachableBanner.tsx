import { Feather } from '@expo/vector-icons';
import { StyleSheet, Text, View } from 'react-native';

import { colors, radii, spacing } from '../lib/theme';

/** Every polling screen shows this on a fetch failure instead of a raw
 * error string — the underlying error (network blip, wrong pairing, server
 * down) isn't actionable detail for the user, "can't reach the server" is. */
export function ServerUnreachableBanner() {
  return (
    <View style={styles.container}>
      <Feather name="wifi-off" size={14} color={colors.amber} />
      <Text style={styles.text}>Can't reach the server — check your connection</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: 'rgba(251,191,36,0.1)',
    borderColor: 'rgba(251,191,36,0.3)',
    borderWidth: 1,
    borderRadius: radii.sm,
    marginHorizontal: spacing.base,
    marginTop: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  text: { color: colors.amber, fontSize: 12, flex: 1 },
});
