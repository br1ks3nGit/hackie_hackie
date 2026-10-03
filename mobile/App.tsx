import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, StyleSheet, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { theme } from './src/theme';
import { LanguageProvider, useLanguage } from './src/i18n';
import { BottomTabBar } from './src/ui';
import { API_BASE_URL } from './src/config';
import { registerDriver, giveConsent } from './src/api/client';
import { HomeScreen } from './src/screens/HomeScreen';
import { TripsScreen } from './src/screens/TripsScreen';
import { CoachScreen } from './src/screens/CoachScreen';
import { PrivacyScreen } from './src/screens/PrivacyScreen';

const STORAGE_KEYS = {
  DRIVER_ID: 'drivescore:driver_id',
  API_KEY: 'drivescore:api_key',
};

type TabKey = 'home' | 'trips' | 'coach' | 'privacy';

export default function App() {
  return (
    <SafeAreaProvider>
      <LanguageProvider>
        <Main />
      </LanguageProvider>
    </SafeAreaProvider>
  );
}

function useApiKey(): { apiKey: string | null; failed: boolean; retry: () => void } {
  const { t } = useLanguage();
  const tRef = useRef(t);
  tRef.current = t;
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const init = async () => {
      setFailed(false);
      try {
        const storedDriverId = await AsyncStorage.getItem(STORAGE_KEYS.DRIVER_ID);
        const storedApiKey = await AsyncStorage.getItem(STORAGE_KEYS.API_KEY);
        if (storedDriverId && storedApiKey) {
          setApiKey(storedApiKey);
          return;
        }
        const response = await registerDriver();
        await AsyncStorage.setItem(STORAGE_KEYS.DRIVER_ID, response.driver_id);
        await AsyncStorage.setItem(STORAGE_KEYS.API_KEY, response.api_key);
        await giveConsent(response.api_key);
        setApiKey(response.api_key);
      } catch (err) {
        console.error('Failed to initialize driver', err);
        setFailed(true);
        Alert.alert(
          tRef.current('setupErrorTitle'),
          tRef.current('setupErrorBody', { url: API_BASE_URL }),
        );
      }
    };
    init();
  }, [attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { apiKey, failed, retry };
}

function Main() {
  const { t } = useLanguage();
  const { apiKey, failed, retry } = useApiKey();
  const [tab, setTab] = useState<TabKey>('home');
  const [tripId, setTripId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const bumpRefresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  // Leaving the Trips tab, or tapping it while active, returns to the list
  const changeTab = (next: TabKey) => {
    if (next !== 'trips' || tab === 'trips') setTripId(null);
    setTab(next);
  };

  const openTrip = useCallback((id: string) => {
    setTripId(id);
    setTab('trips');
  }, []);

  const tabs: { key: TabKey; label: string }[] = [
    { key: 'home', label: t('tabHome') },
    { key: 'trips', label: t('tabTrips') },
    { key: 'coach', label: t('tabCoach') },
    { key: 'privacy', label: t('tabPrivacy') },
  ];

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'left', 'right']}>
      {/* Home stays mounted (hidden) so recording state survives tab switches */}
      <View style={tab === 'home' ? styles.flex1 : styles.hidden}>
        <HomeScreen
          apiKey={apiKey}
          active={tab === 'home'}
          onViewAll={() => changeTab('trips')}
          onOpenTrip={openTrip}
          setupFailed={failed}
          onRetrySetup={retry}
          onTripProcessed={bumpRefresh}
        />
      </View>
      {tab === 'trips' ? (
        <TripsScreen
          apiKey={apiKey}
          selectedId={tripId}
          onSelect={setTripId}
          refreshKey={refreshKey}
          setupFailed={failed}
          onRetrySetup={retry}
        />
      ) : null}
      {tab === 'coach' ? <CoachScreen /> : null}
      {tab === 'privacy' ? <PrivacyScreen /> : null}
      <BottomTabBar tabs={tabs} active={tab} onChange={changeTab} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: theme.colors.cream },
  flex1: { flex: 1 },
  hidden: { display: 'none' },
});
