import { Tabs } from 'expo-router';
import { Text } from 'react-native';

import { colors } from '../../lib/theme';

function TabIcon({ emoji }: { emoji: string }) {
  return <Text style={{ fontSize: 20 }}>{emoji}</Text>;
}

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.faint,
        tabBarStyle: { backgroundColor: colors.panel, borderTopColor: colors.hair },
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Feed', tabBarIcon: () => <TabIcon emoji="📡" /> }} />
      <Tabs.Screen name="ptt" options={{ title: 'Talk', tabBarIcon: () => <TabIcon emoji="🎙" /> }} />
      <Tabs.Screen name="actions" options={{ title: 'Actions', tabBarIcon: () => <TabIcon emoji="⚡" /> }} />
      <Tabs.Screen name="memory" options={{ title: 'Memory', tabBarIcon: () => <TabIcon emoji="🧠" /> }} />
    </Tabs>
  );
}
