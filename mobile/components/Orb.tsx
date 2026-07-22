import { LinearGradient } from 'expo-linear-gradient';
import { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, StyleSheet, View } from 'react-native';

import { orbStops } from '../lib/theme';
import { RadialGlow } from './RadialGlow';

type OrbProps = {
  /** Diameter of the glowing sphere itself. */
  size?: number;
  /** The 2–3 faint concentric rings around the sphere (hero PTT screen only). */
  showRings?: boolean;
};

/** The glowing ambient orb — "Nala is here". A gentle float + glow pulse
 * loop (skipped under Reduce Motion), reused at hero size on the voice
 * screen and small size on onboarding. */
export function Orb({ size = 148, showRings = true }: OrbProps) {
  const float = useRef(new Animated.Value(0)).current;
  const glow = useRef(new Animated.Value(0)).current;
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then(setReduceMotion);
  }, []);

  useEffect(() => {
    if (reduceMotion) return;
    const floatLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(float, { toValue: 1, duration: 2750, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
        Animated.timing(float, { toValue: 0, duration: 2750, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
      ])
    );
    const glowLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(glow, { toValue: 1, duration: 1800, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
        Animated.timing(glow, { toValue: 0, duration: 1800, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
      ])
    );
    floatLoop.start();
    glowLoop.start();
    return () => {
      floatLoop.stop();
      glowLoop.stop();
    };
  }, [reduceMotion, float, glow]);

  const wrapSize = Math.round(size * 1.24);
  const translateY = float.interpolate({ inputRange: [0, 1], outputRange: [0, -Math.round(size * 0.05)] });
  const glowOpacity = glow.interpolate({ inputRange: [0, 1], outputRange: [0.75, 1] });
  const glowScale = glow.interpolate({ inputRange: [0, 1], outputRange: [1, 1.08] });

  return (
    <View style={[styles.wrap, { width: wrapSize, height: wrapSize }]}>
      <Animated.View style={[styles.center, { opacity: glowOpacity, transform: [{ scale: glowScale }] }]}>
        <RadialGlow rgb="167,139,250" opacity={0.55} size={size * 2.1} />
      </Animated.View>
      <Animated.View style={[styles.center, { opacity: glowOpacity, transform: [{ scale: glowScale }] }]}>
        <RadialGlow rgb="56,189,248" opacity={0.35} size={size * 1.7} />
      </Animated.View>

      {showRings ? (
        <>
          <View style={[styles.ring, { width: wrapSize, height: wrapSize, borderRadius: wrapSize / 2, borderColor: 'rgba(196,181,253,0.08)' }]} />
          <View
            style={[
              styles.ring,
              { width: wrapSize - 24, height: wrapSize - 24, borderRadius: (wrapSize - 24) / 2, borderColor: 'rgba(120,180,255,0.14)' },
            ]}
          />
          <View
            style={[
              styles.ring,
              { width: size + 4, height: size + 4, borderRadius: (size + 4) / 2, borderColor: 'rgba(196,181,253,0.2)' },
            ]}
          />
        </>
      ) : null}

      <Animated.View style={{ transform: [{ translateY }] }}>
        <LinearGradient
          colors={orbStops as unknown as [string, string, ...string[]]}
          locations={[0, 0.34, 0.62, 1]}
          start={{ x: 0.2, y: 0.15 }}
          end={{ x: 0.95, y: 1 }}
          style={[styles.orb, { width: size, height: size, borderRadius: size / 2 }]}
        >
          <View style={[styles.highlight, { width: size * 0.4, height: size * 0.4, borderRadius: (size * 0.4) / 2 }]} />
        </LinearGradient>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'center', justifyContent: 'center' },
  center: { position: 'absolute', alignItems: 'center', justifyContent: 'center' },
  ring: { position: 'absolute', borderWidth: 1 },
  orb: { overflow: 'hidden' },
  highlight: { position: 'absolute', top: '12%', left: '14%', backgroundColor: 'rgba(255,255,255,0.35)' },
});
