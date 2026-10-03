import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  Switch,
  Pressable,
  Alert,
  ScrollView,
  AccessibilityInfo,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { theme, switchColors } from './src/theme';
import { styles } from './src/appStyles';
import { Card, CardSm, PrimaryButton, SecondaryButton } from './src/ui';
import { LanguageProvider, useLanguage, localeFor, eventLabel, trendLabel, Language } from './src/i18n';
import { LanguagePicker } from './src/LanguagePicker';
import { API_BASE_URL } from './src/config';
import { TripDetector } from './src/sensors/TripDetector';
import { startSensors, stopSensors } from './src/sensors/SensorManager';
import {
  registerDriver,
  giveConsent,
  startTrip,
  endTrip,
  getDriverSummary,
  getTripDetail,
  getTripStatus,
  getMyTrips,
  labelTrip,
  DriverSummaryResponse,
  TripListItem,
  TripDetailResponse,
} from './src/api/client';
import AsyncStorage from '@react-native-async-storage/async-storage';

const RELABEL_REFRESH_MS = 5000;

function formatTime(iso: string, language: Language): string {
  return new Date(iso).toLocaleTimeString(localeFor(language), {
    hour: '2-digit',
    minute: '2-digit',
  });
}

const TIER_COLORS: Record<string, { soft: string; ink: string }> = theme.colors.tier;

const STORAGE_KEYS = {
  DRIVER_ID: 'drivescore:driver_id',
  API_KEY: 'drivescore:api_key',
  DRIVING_MODE: 'drivescore:driving_mode',
};

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
  const { language, t } = useLanguage();
  const tRef = useRef(t);
  tRef.current = t;
  const [recording, setRecording] = useState(false);
  const [inTrip, setInTrip] = useState(false);
  const [currentTripId, setCurrentTripId] = useState<string | null>(null);
  const [driverId, setDriverId] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [summary, setSummary] = useState<DriverSummaryResponse | null>(null);
  const [lastTrip, setLastTrip] = useState<TripDetailResponse | null>(null);
  const [chunkCount, setChunkCount] = useState(0);

  const [drivingMode, setDrivingMode] = useState(false);
  const [toConfirm, setToConfirm] = useState<TripListItem[]>([]);
  const [labelling, setLabelling] = useState(false);
  const [labelMessage, setLabelMessage] = useState<'removed' | 'added' | null>(null);
  const [labelError, setLabelError] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const { fontScale } = useWindowDimensions();
  const stackButtons = fontScale > 1.3;
  // flex: 1 only in a row: in a stacked column it would collapse the buttons to min height
  const btnFlex = stackButtons ? undefined : styles.flex1;

  const detectorRef = useRef<TripDetector | null>(null);
  // Read by TripDetector at chunk-build time, so flipping mid-trip applies to the next chunk
  const drivingModeRef = useRef(false);
  // Set once the user toggles, so a late AsyncStorage load cannot overwrite their choice
  const touchedRef = useRef(false);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    },
    [],
  );

  useEffect(() => {
    initializeDriver();
    AsyncStorage.getItem(STORAGE_KEYS.DRIVING_MODE)
      .then((value) => {
        if (touchedRef.current) return;
        drivingModeRef.current = value === 'true';
        setDrivingMode(value === 'true');
      })
      .catch((err) => console.warn('Could not read driving mode', err));
  }, []);

  const changeDrivingMode = (value: boolean) => {
    touchedRef.current = true;
    drivingModeRef.current = value;
    setDrivingMode(value);
    AsyncStorage.setItem(STORAGE_KEYS.DRIVING_MODE, String(value)).catch((err) =>
      console.warn('Could not save driving mode', err),
    );
  };

  const initializeDriver = async () => {
    try {
      // Load stored credentials
      const storedDriverId = await AsyncStorage.getItem(STORAGE_KEYS.DRIVER_ID);
      const storedApiKey = await AsyncStorage.getItem(STORAGE_KEYS.API_KEY);

      if (storedDriverId && storedApiKey) {
        setDriverId(storedDriverId);
        setApiKey(storedApiKey);
        await refreshSummary(storedApiKey);
        await refreshToConfirm(storedApiKey);
        return;
      }

      // Register new driver
      const response = await registerDriver();
      setDriverId(response.driver_id);
      setApiKey(response.api_key);

      await AsyncStorage.setItem(STORAGE_KEYS.DRIVER_ID, response.driver_id);
      await AsyncStorage.setItem(STORAGE_KEYS.API_KEY, response.api_key);

      // Give consent
      await giveConsent(response.api_key);
      await refreshSummary(response.api_key);
      await refreshToConfirm(response.api_key);
    } catch (err) {
      console.error('Failed to initialize driver', err);
      Alert.alert(
        tRef.current('setupErrorTitle'),
        tRef.current('setupErrorBody', { url: API_BASE_URL }),
      );
    }
  };

  const refreshSummary = async (key: string) => {
    try {
      const data = await getDriverSummary(key);
      setSummary(data);
    } catch (err) {
      console.warn('Could not fetch summary', err);
    }
  };

  const refreshToConfirm = async (key: string) => {
    try {
      const trips = await getMyTrips(key);
      setToConfirm(trips.filter((t) => t.needs_confirmation));
      setLoadError(false);
    } catch (err) {
      console.warn('Could not fetch trips to confirm', err);
      setLoadError(true);
    }
  };

  const confirmTrip = async (trip: TripListItem, tripType: 'driver' | 'passenger') => {
    if (!apiKey || labelling) return;
    setLabelling(true);
    setLabelMessage(null);
    setLabelError(false);
    try {
      const res = await labelTrip(trip.trip_id, tripType, apiKey);
      const removed = res.status === 'removed_from_score';
      setLabelMessage(removed ? 'removed' : 'added');
      AccessibilityInfo.announceForAccessibility(
        tRef.current(removed ? 'savedRemoved' : 'savedAdded'),
      );
      setToConfirm((rows) => rows.filter((r) => r.trip_id !== trip.trip_id));
      await refreshSummary(apiKey);
      // Driver relabel reprocesses in the background; refresh again shortly
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = setTimeout(() => {
        refreshTimerRef.current = null;
        if (!apiKey) return;
        refreshSummary(apiKey);
        refreshToConfirm(apiKey);
      }, RELABEL_REFRESH_MS);
    } catch (err) {
      console.warn('Could not label trip', err);
      setLabelError(true);
      AccessibilityInfo.announceForAccessibility(tRef.current('saveError'));
    } finally {
      setLabelling(false);
    }
  };

  const setupDetector = () => {
    detectorRef.current = new TripDetector({
      isDriving: () => drivingModeRef.current,
      onTripStart: (tripId) => {
        setInTrip(true);
        setCurrentTripId(tripId);
      },
      onTripEnd: async (tripId) => {
        setInTrip(false);
        setCurrentTripId(null);

        if (apiKey) {
          try {
            await endTrip(tripId, apiKey);
            // Poll until the backend finishes processing (up to ~60 s)
            let status = 'processing';
            for (let i = 0; i < 30 && status === 'processing'; i++) {
              await new Promise(resolve => setTimeout(resolve, 2000));
              status = (await getTripStatus(tripId, apiKey)).status;
            }
            await refreshSummary(apiKey);
            await refreshToConfirm(apiKey);
            setLastTrip(await getTripDetail(tripId, apiKey));
          } catch (err) {
            console.error('Failed to end trip', err);
          }
        }
      },
      onChunkUploaded: (seq) => {
        setChunkCount(seq + 1);
      },
    });
  };

  const toggleRecording = async () => {
    if (recording) {
      stopSensors();
      setRecording(false);
      // forceEnd awaits the final chunk upload (with retries); onTripEnd —
      // which sends /end — fires only after the last chunk is acknowledged
      await detectorRef.current?.forceEnd();
      return;
    }

    if (!apiKey) {
      Alert.alert(t('notReadyTitle'), t('notReadyBody'));
      return;
    }

    try {
      setupDetector();

      // Start trip on server
      const tripResponse = await startTrip(apiKey);
      await detectorRef.current?.forceStart(tripResponse.trip_id, apiKey);

      await startSensors(
        (sample) => detectorRef.current?.addAccelSample(sample),
        (sample) => detectorRef.current?.addGyroSample(sample),
        (point) => detectorRef.current?.addGpsPoint(point)
      );

      setRecording(true);
      setChunkCount(0);
    } catch (err) {
      Alert.alert(t('errorTitle'), t('startError'));
      console.error(err);
    }
  };

  const tier = TIER_COLORS[summary?.tier.toUpperCase() ?? ''] ?? TIER_COLORS.fallback;
  const messageText = labelError
    ? t('saveError')
    : loadError
      ? t('loadError')
      : labelMessage === 'removed'
        ? t('savedRemoved')
        : labelMessage === 'added'
          ? t('savedAdded')
          : '';
  const isError = labelError || loadError;
  const messageColors = isError ? theme.colors.danger : theme.colors.success;

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
        <Text style={styles.eyebrow}>{t('visitorCover')}</Text>
        <Text style={styles.title}>BT</Text>
        <LanguagePicker />
        {driverId && (
          <Text style={[styles.caption, styles.section]}>
            {t('driverLabel', { id: driverId.substring(0, 12) })}
          </Text>
        )}

        {summary && (
          <Card style={styles.section}>
            <Text style={styles.caption}>{t('yourScore')}</Text>
            <View style={styles.scoreRow}>
              <Text style={styles.display}>{summary.score}</Text>
              <View
                style={[styles.chip, { backgroundColor: tier.soft }]}
                accessible
                accessibilityLabel={t('tierLabel', { tier: summary.tier })}
              >
                <Text style={[theme.type.chip, { color: tier.ink }]}>{summary.tier}</Text>
              </View>
            </View>
            <Text style={styles.body}>
              {t('premiumMultiplier', { value: summary.premium_multiplier })}
            </Text>
            <Text style={styles.body}>{t('trendLine', { value: trendLabel(t, summary.trend) })}</Text>
            <Text style={styles.body}>{t('trips90d', { count: summary.total_trips_90d })}</Text>
          </Card>
        )}

        <CardSm style={[styles.section, styles.switchCard]}>
          <Pressable
            style={styles.switchRow}
            onPress={() => changeDrivingMode(!drivingMode)}
            accessibilityRole="switch"
            accessibilityState={{ checked: drivingMode }}
            accessibilityLabel={t('drivingModeLabel')}
          >
            <Text style={styles.bodyStrong}>
              {t('drivingModeState', { state: t(drivingMode ? 'on' : 'off') })}
            </Text>
            <Switch
              value={drivingMode}
              onValueChange={changeDrivingMode}
              accessible={false}
              trackColor={{ true: switchColors.on, false: switchColors.off }}
              thumbColor={switchColors.thumb}
            />
          </Pressable>
        </CardSm>
        <Text style={[styles.caption, styles.section]}>
          {t('drivingModeHint')}
        </Text>

        <PrimaryButton
          style={styles.section}
          danger={recording}
          label={t(recording ? 'stopRecording' : 'startRecording')}
          onPress={toggleRecording}
          accessibilityRole="button"
          accessibilityLabel={t(recording ? 'stopRecording' : 'startRecording')}
        />

        {recording && (
          <CardSm bg={theme.colors.success.soft} style={styles.section}>
            <Text style={styles.successStrong}>{t('recordingTrip')}</Text>
            <Text style={styles.successText}>
              {t('statusLine', { value: t(inTrip ? 'statusInTrip' : 'statusIdle') })}
            </Text>
            <Text style={styles.successText}>
              {t('drivingLine', { value: t(drivingMode ? 'yes' : 'no') })}
            </Text>
            <Text style={styles.successText}>{t('chunksUploaded', { count: chunkCount })}</Text>
            {currentTripId && (
              <Text style={styles.successText}>
                {t('tripIdLine', { id: currentTripId.substring(0, 16) })}
              </Text>
            )}
          </CardSm>
        )}

        <Text
          style={
            messageText
              ? [styles.message, { backgroundColor: messageColors.soft, color: messageColors.ink }]
              : undefined
          }
          accessibilityLiveRegion="polite"
        >
          {messageText}
        </Text>
        {loadError && apiKey && (
          <Pressable
            style={styles.retry}
            onPress={() => refreshToConfirm(apiKey)}
            accessibilityRole="button"
            accessibilityLabel={t('retryLabel')}
          >
            <Text style={[styles.bodyStrong, { color: theme.colors.jadeInk }]}>{t('retry')}</Text>
          </Pressable>
        )}

        {toConfirm.length > 0 && (
          <Card bg={theme.colors.warning.soft} style={styles.section}>
            <Text style={styles.warningHeader} accessibilityRole="header">
              {t('tripsToConfirm')}
            </Text>
            {toConfirm.map((trip) => {
              const started = new Date(trip.started_at);
              const time = formatTime(trip.started_at, language);
              const date = started.toLocaleDateString(localeFor(language), {
                weekday: 'short',
                day: 'numeric',
                month: 'short',
              });
              return (
                <CardSm key={trip.trip_id} style={styles.tripRow}>
                  <Text style={styles.bodyStrong}>
                    {date} {time}
                    {'\n'}
                    {t('kmValue', { km: trip.distance_km.toFixed(1) })}
                  </Text>
                  <View style={stackButtons ? styles.colGap : styles.rowGap}>
                    <PrimaryButton
                      style={btnFlex}
                      label={t('iWasDriving')}
                      disabled={labelling}
                      onPress={() => confirmTrip(trip, 'driver')}
                      accessibilityRole="button"
                      accessibilityLabel={t('iWasDrivingA11y', { date, time })}
                      accessibilityState={{ disabled: labelling }}
                    />
                    <SecondaryButton
                      style={btnFlex}
                      label={t('iWasPassenger')}
                      disabled={labelling}
                      onPress={() => confirmTrip(trip, 'passenger')}
                      accessibilityRole="button"
                      accessibilityLabel={t('iWasPassengerA11y', { date, time })}
                      accessibilityState={{ disabled: labelling }}
                    />
                  </View>
                </CardSm>
              );
            })}
          </Card>
        )}

        {lastTrip && (
          <Card style={[styles.section, styles.lastTrip]}>
            <Text style={styles.bodyStrong}>{t('lastTrip')}</Text>
            <Text style={styles.body}>
              {t('scoreLine', { value: lastTrip.score ?? t('notAvailable') })}
            </Text>
            <Text style={styles.body}>
              {t('distanceLine', { km: lastTrip.distance_km.toFixed(2) })}
            </Text>
            <Text style={styles.body}>
              {t('durationLine', { min: lastTrip.duration_min.toFixed(1) })}
            </Text>
            {lastTrip.explanation && <Text style={styles.explanation}>{lastTrip.explanation}</Text>}
            <Text style={styles.body}>{t('eventsLine', { count: lastTrip.events.length })}</Text>
            {lastTrip.events.map((e, idx) => (
              <Text key={idx} style={styles.caption}>
                {eventLabel(t, e.type)} {e.peak_g ? `(${e.peak_g.toFixed(2)}g)` : ''}
              </Text>
            ))}
          </Card>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}
