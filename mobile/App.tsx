import React, { useCallback, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { theme } from './src/theme';
import { LanguageProvider, useLanguage } from './src/i18n';
import { BottomTabBar } from './src/ui';
import { AppHeader } from './src/AppHeader';
import { OfflineBanner } from './src/uiBlocks';
import { useSession } from './src/useSession';
import { OnboardingScreen } from './src/screens/OnboardingScreen';
import { HomeScreen } from './src/screens/HomeScreen';
import { TripsScreen } from './src/screens/TripsScreen';
import { CoachScreen } from './src/screens/CoachScreen';
import { PrivacyScreen } from './src/screens/PrivacyScreen';

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

function Main() {
  const { t } = useLanguage();
  const { status, apiKey, failed, retry, completeOnboarding, signOutAfterDelete } = useSession();
  const [tab, setTab] = useState<TabKey>('home');
  const [tripId, setTripId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [recording, setRecording] = useState(false);
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

  const afterDelete = useCallback(async () => {
    setTab('home');
    setTripId(null);
    await signOutAfterDelete();
  }, [signOutAfterDelete]);

  const tabs: { key: TabKey; label: string }[] = [
    { key: 'home', label: t('tabHome') },
    { key: 'trips', label: t('tabTrips') },
    { key: 'coach', label: t('tabCoach') },
    { key: 'privacy', label: t('tabPrivacy') },
  ];

  if (status === 'loading') {
    return (
      <View
        style={styles.loading}
        accessibilityLabel={t('loading')}
        accessibilityLiveRegion="polite"
      >
        <ActivityIndicator color={theme.colors.jadeDeep} size="large" />
      </View>
    );
  }
  if (status === 'onboarding') {
    return (
      <SafeAreaView style={styles.screen} edges={['top', 'left', 'right']}>
        <AppHeader />
        <OnboardingScreen onComplete={completeOnboarding} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'left', 'right']}>
      <AppHeader />
      <OfflineBanner />
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
          onRecordingChange={setRecording}
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
      {tab === 'privacy' ? (
        <PrivacyScreen apiKey={apiKey} recording={recording} onDeleted={afterDelete} />
      ) : null}
      <BottomTabBar tabs={tabs} active={tab} onChange={changeTab} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: theme.colors.cream },
  loading: { flex: 1, backgroundColor: theme.colors.cream, justifyContent: 'center' },
  flex1: { flex: 1 },
  hidden: { display: 'none' },
});
