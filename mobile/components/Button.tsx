import { LinearGradient } from 'expo-linear-gradient';
import { ActivityIndicator, Pressable, StyleSheet, Text, type StyleProp, type ViewStyle } from 'react-native';

import { accentGradient, accentOnColor, colors, radii, spacing } from '../lib/theme';

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
  primary: accentOnColor,
  ghost: colors.ink,
  danger: colors.red,
};

/** Primary renders the violet→cyan accent gradient (dark ink on top, per
 * the Ambient direction); ghost/danger stay flat glass fills. */
export function Button({ label, onPress, variant = 'primary', loading, disabled, style }: ButtonProps) {
  const textColor = TEXT_COLOR[variant];
  const content = loading ? (
    <ActivityIndicator color={textColor} />
  ) : (
    <Text style={[styles.label, { color: textColor }]}>{label}</Text>
  );

  if (variant === 'primary') {
    return (
      <Pressable
        onPress={onPress}
        disabled={disabled || loading}
        style={({ pressed }) => [style, (disabled || loading) && styles.disabled, pressed && !disabled && !loading && styles.pressed]}
      >
        <LinearGradient colors={accentGradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={[styles.base, styles.primaryShadow]}>
          {content}
        </LinearGradient>
      </Pressable>
    );
  }

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
      {content}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: radii.lg,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.base,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 48,
    flexDirection: 'row',
    gap: spacing.sm,
  },
  primaryShadow: {
    shadowColor: '#a78bfa',
    shadowOpacity: 0.5,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    elevation: 4,
  },
  ghost: { backgroundColor: colors.panel2, borderWidth: 1, borderColor: colors.hair },
  danger: { backgroundColor: 'rgba(248,113,113,0.12)', borderWidth: 1, borderColor: 'rgba(248,113,113,0.3)' },
  disabled: { opacity: 0.5 },
  pressed: { opacity: 0.85 },
  label: { fontWeight: '700', fontSize: 15 },
});
