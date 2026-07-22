import { StyleSheet, View } from 'react-native';

type RadialGlowProps = {
  /** "R,G,B" — plugged into rgba(...) for each ring. */
  rgb: string;
  /** Opacity at the glow's core; falls off across the outer rings. */
  opacity: number;
  /** Diameter of the outermost, faintest ring. */
  size: number;
  style?: object;
};

/** A soft circular glow, faked with three concentric, decreasingly-large,
 * increasingly-opaque circles — React Native has no cheap radial-gradient
 * or blur-a-solid-color primitive, so this is the standard approximation.
 * Reused for the ambient ground glows and the orb's outer glow. */
export function RadialGlow({ rgb, opacity, size, style }: RadialGlowProps) {
  return (
    <View style={[styles.center, { width: size, height: size }, style]} pointerEvents="none">
      <View
        style={[
          styles.ring,
          { width: size, height: size, borderRadius: size / 2, backgroundColor: `rgba(${rgb},${opacity * 0.35})` },
        ]}
      />
      <View
        style={[
          styles.ring,
          {
            width: size * 0.66,
            height: size * 0.66,
            borderRadius: (size * 0.66) / 2,
            backgroundColor: `rgba(${rgb},${opacity * 0.65})`,
          },
        ]}
      />
      <View
        style={[
          styles.ring,
          {
            width: size * 0.36,
            height: size * 0.36,
            borderRadius: (size * 0.36) / 2,
            backgroundColor: `rgba(${rgb},${opacity})`,
          },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  center: { alignItems: 'center', justifyContent: 'center' },
  ring: { position: 'absolute' },
});
