import { Stack, useRouter, useSegments } from 'expo-router';
import { useEffect } from 'react';
import { ActivityIndicator, StatusBar, StyleSheet, View } from 'react-native';

import { PairingProvider, usePairingContext } from '../lib/PairingContext';
import { colors } from '../lib/theme';

function RootNavigator() {
  const { isPaired, isLoading } = usePairingContext();
  const router = useRouter();
  const segments = useSegments();

  useEffect(() => {
    if (isLoading) return;
    const inOnboarding = segments[0] === 'onboarding';
    if (!isPaired && !inOnboarding) {
      router.replace('/onboarding');
    } else if (isPaired && inOnboarding) {
      router.replace('/(tabs)');
    }
  }, [isLoading, isPaired, segments, router]);

  if (isLoading) {
    return (
      <View style={styles.loading}>
        <ActivityIndicator color={colors.accent} />
      </View>
    );
  }

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="onboarding" />
      <Stack.Screen name="(tabs)" />
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <PairingProvider>
      <StatusBar barStyle="light-content" backgroundColor={colors.base} />
      <RootNavigator />
    </PairingProvider>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, backgroundColor: colors.base, alignItems: 'center', justifyContent: 'center' },
});
