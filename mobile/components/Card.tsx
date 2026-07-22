import { StyleSheet, View, type ViewProps } from 'react-native';

import { colors, radii, spacing } from '../lib/theme';

export function Card({ style, children, ...rest }: ViewProps) {
  return (
    <View style={[styles.card, style]} {...rest}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.panel2,
    borderColor: colors.hair,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.base,
  },
});
