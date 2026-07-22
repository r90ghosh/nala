import { ActivityIndicator, Pressable, StyleSheet, Text, type StyleProp, type ViewStyle } from 'react-native';

import { colors, radii, spacing } from '../lib/theme';

type ButtonVariant = 'primary' | 'ghost' | 'danger';

type ButtonProps = {
  label: string;
  onPress: () => void;
  variant?: ButtonVariant;
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
};

const TEXT_COLOR: Record<ButtonVariant, string> = {
  primary: colors.base,
  ghost: colors.ink,
  danger: colors.red,
};

export function Button({ label, onPress, variant = 'primary', loading, disabled, style }: ButtonProps) {
  const textColor = TEXT_COLOR[variant];
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.base,
        styles[variant],
        style,
        (disabled || loading) && styles.disabled,
        pressed && !disabled && !loading && styles.pressed,
      ]}
    >
      {loading ? <ActivityIndicator color={textColor} /> : <Text style={[styles.label, { color: textColor }]}>{label}</Text>}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: radii.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.base,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 48,
    flexDirection: 'row',
    gap: spacing.sm,
  },
  primary: { backgroundColor: colors.accent },
  ghost: { backgroundColor: colors.panel2, borderWidth: 1, borderColor: colors.hair },
  danger: { backgroundColor: 'rgba(248,113,113,0.12)', borderWidth: 1, borderColor: 'rgba(248,113,113,0.3)' },
  disabled: { opacity: 0.5 },
  pressed: { opacity: 0.85 },
  label: { fontWeight: '700', fontSize: 15 },
});
