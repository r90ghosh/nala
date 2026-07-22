import { Feather } from '@expo/vector-icons';
import { Tabs } from 'expo-router';
import { StyleSheet } from 'react-native';

import { colors } from '../../lib/theme';

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.faint,
        tabBarStyle: styles.tabBar,
        tabBarLabelStyle: styles.tabLabel,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: 'Feed', tabBarIcon: ({ color, size }) => <Feather name="radio" size={size} color={color} /> }}
      />
      <Tabs.Screen
        name="ptt"
        options={{ title: 'Talk', tabBarIcon: ({ color, size }) => <Feather name="mic" size={size} color={color} /> }}
      />
      <Tabs.Screen
        name="actions"
        options={{ title: 'Actions', tabBarIcon: ({ color, size }) => <Feather name="zap" size={size} color={color} /> }}
      />
      <Tabs.Screen
        name="memory"
        options={{ title: 'Memory', tabBarIcon: ({ color, size }) => <Feather name="cpu" size={size} color={color} /> }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    backgroundColor: colors.panel,
    borderTopColor: colors.hair,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  tabLabel: { fontSize: 10.5, fontWeight: '600' },
});
