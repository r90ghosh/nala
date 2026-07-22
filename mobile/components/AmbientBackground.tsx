import { LinearGradient } from 'expo-linear-gradient';
import { StyleSheet, View } from 'react-native';

import { ground, glows } from '../lib/theme';
import { RadialGlow } from './RadialGlow';

/** The ambient ground every screen sits on: a near-black vertical gradient
 * with soft violet/cyan/pink glows. Absolutely fills its parent — render it
 * as the first child of a `flex: 1, overflow: 'hidden'` container. */
export function AmbientBackground() {
  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="none">
      <LinearGradient colors={[ground.top, ground.bottom]} style={StyleSheet.absoluteFill} />
      <RadialGlow
        rgb={glows.violetTop.rgb}
        opacity={glows.violetTop.opacity}
        size={520}
        style={styles.violetTop}
      />
      <RadialGlow
        rgb={glows.cyanBottomRight.rgb}
        opacity={glows.cyanBottomRight.opacity}
        size={480}
        style={styles.cyanBottomRight}
      />
      <RadialGlow
        rgb={glows.pinkBottomLeft.rgb}
        opacity={glows.pinkBottomLeft.opacity}
        size={400}
        style={styles.pinkBottomLeft}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  violetTop: { position: 'absolute', top: '-6%', left: '50%', marginLeft: -260 },
  cyanBottomRight: { position: 'absolute', bottom: '-4%', right: '-18%' },
  pinkBottomLeft: { position: 'absolute', bottom: '4%', left: '-22%' },
});
