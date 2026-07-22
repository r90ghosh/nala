import { StyleSheet, View, type ViewProps } from 'react-native';

import { colors, radii, spacing } from '../lib/theme';

/** A glass card: translucent fill, a hairline border with a brighter top
 * edge (fakes the glass "inner highlight" React Native can't do with a real
 * inset shadow), generous radius, soft drop shadow. */
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
    borderTopColor: 'rgba(255,255,255,0.22)',
    borderWidth: 1,
    borderRadius: radii.xl,
    padding: spacing.base,
    shadowColor: '#000',
    shadowOpacity: 0.35,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 10 },
    elevation: 4,
  },
});
