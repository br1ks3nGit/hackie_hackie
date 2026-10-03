import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  Switch,
  Pressable,
  StyleSheet,
  Alert,
  ScrollView,
  AccessibilityInfo,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { theme, switchColors } from './src/theme';
import { Card, CardSm, PrimaryButton, SecondaryButton } from './src/ui';
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
const LOAD_ERROR_TEXT = 'Error: Could not load trips to confirm.';

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
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
      <Main />
    </SafeAreaProvider>
  );
}

function Main() {
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
  const [labelMessage, setLabelMessage] = useState<string | null>(null);
  const [labelError, setLabelError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
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
        'Setup Error',
        `Could not reach ${API_BASE_URL}. Make sure the backend is running and set ` +
          'EXPO_PUBLIC_API_BASE_URL to http://<laptop LAN IP>:8000',
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
      setLoadError(null);
    } catch (err) {
      console.warn('Could not fetch trips to confirm', err);
      setLoadError(LOAD_ERROR_TEXT);
    }
  };

  const confirmTrip = async (trip: TripListItem, tripType: 'driver' | 'passenger') => {
    if (!apiKey || labelling) return;
    setLabelling(true);
    setLabelMessage(null);
    setLabelError(null);
    try {
      const res = await labelTrip(trip.trip_id, tripType, apiKey);
      const msg =
        res.status === 'removed_from_score'
          ? 'Saved: Removed from your score'
          : 'Saved: Added to your score';
      setLabelMessage(msg);
      AccessibilityInfo.announceForAccessibility(msg);
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
      const msg = 'Error: Could not save your answer. Please try again.';
      setLabelError(msg);
      AccessibilityInfo.announceForAccessibility(msg);
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
      Alert.alert('Not ready', 'Please wait for driver setup to complete.');
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
      Alert.alert('Error', 'Could not start recording. Check permissions.');
      console.error(err);
    }
  };

  const tier = TIER_COLORS[summary?.tier.toUpperCase() ?? ''] ?? TIER_COLORS.fallback;
  const messageText = labelError ?? loadError ?? labelMessage ?? '';
  const isError = Boolean(labelError || loadError);
  const messageColors = isError ? theme.colors.danger : theme.colors.success;

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
        <Text style={styles.eyebrow}>Hong Kong visitor motor cover</Text>
        <Text style={styles.title}>BT</Text>
        {driverId && <Text style={styles.caption}>Driver: {driverId.substring(0, 12)}...</Text>}

        {summary && (
          <Card style={styles.section}>
            <Text style={styles.caption}>Your Score</Text>
            <View style={styles.scoreRow}>
              <Text style={styles.display}>{summary.score}</Text>
              <View
                style={[styles.chip, { backgroundColor: tier.soft }]}
                accessible
                accessibilityLabel={`Tier ${summary.tier}`}
              >
                <Text style={[theme.type.chip, { color: tier.ink }]}>{summary.tier}</Text>
              </View>
            </View>
            <Text style={styles.body}>Premium Multiplier: {summary.premium_multiplier}x</Text>
            <Text style={styles.body}>Trend: {summary.trend}</Text>
            <Text style={styles.body}>Trips (90d): {summary.total_trips_90d}</Text>
          </Card>
        )}

        <CardSm style={[styles.section, styles.switchCard]}>
          <Pressable
            style={styles.switchRow}
            onPress={() => changeDrivingMode(!drivingMode)}
            accessibilityRole="switch"
            accessibilityState={{ checked: drivingMode }}
            accessibilityLabel="I'm driving"
          >
            <Text style={styles.bodyStrong}>I'm driving: {drivingMode ? 'On' : 'Off'}</Text>
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
          Turn on when you are the driver. Trips recorded while off do not count toward your score
          unless you confirm them later.
        </Text>

        <PrimaryButton
          style={styles.section}
          danger={recording}
          label={recording ? 'Stop Recording' : 'Start Recording'}
          onPress={toggleRecording}
          accessibilityRole="button"
          accessibilityLabel={recording ? 'Stop Recording' : 'Start Recording'}
        />

        {recording && (
          <CardSm bg={theme.colors.success.soft} style={styles.section}>
            <Text style={styles.successStrong}>Recording trip</Text>
            <Text style={styles.successText}>
              Status: {inTrip ? 'In trip' : 'Recording (idle)'}
            </Text>
            <Text style={styles.successText}>Driving: {drivingMode ? 'Yes' : 'No'}</Text>
            <Text style={styles.successText}>Chunks uploaded: {chunkCount}</Text>
            {currentTripId && (
              <Text style={styles.successText}>Trip: {currentTripId.substring(0, 16)}...</Text>
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
            accessibilityLabel="Retry loading trips to confirm"
          >
            <Text style={[styles.bodyStrong, { color: theme.colors.jadeInk }]}>Retry</Text>
          </Pressable>
        )}

        {toConfirm.length > 0 && (
          <Card bg={theme.colors.warning.soft} style={styles.section}>
            <Text style={styles.warningHeader} accessibilityRole="header">
              Trips to confirm
            </Text>
            {toConfirm.map((trip) => {
              const started = new Date(trip.started_at);
              const time = formatTime(trip.started_at);
              const date = started.toLocaleDateString([], {
                weekday: 'short',
                day: 'numeric',
                month: 'short',
              });
              return (
                <CardSm key={trip.trip_id} style={styles.tripRow}>
                  <Text style={styles.bodyStrong}>
                    {date} {time}
                    {'\n'}
                    {trip.distance_km.toFixed(1)} km
                  </Text>
                  <View style={stackButtons ? styles.colGap : styles.rowGap}>
                    <PrimaryButton
                      style={btnFlex}
                      label="I was driving"
                      disabled={labelling}
                      onPress={() => confirmTrip(trip, 'driver')}
                      accessibilityRole="button"
                      accessibilityLabel={`I was driving, trip on ${date} at ${time}`}
                      accessibilityState={{ disabled: labelling }}
                    />
                    <SecondaryButton
                      style={btnFlex}
                      label="I was a passenger"
                      disabled={labelling}
                      onPress={() => confirmTrip(trip, 'passenger')}
                      accessibilityRole="button"
                      accessibilityLabel={`I was a passenger, trip on ${date} at ${time}`}
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
            <Text style={styles.bodyStrong}>Last Trip</Text>
            <Text style={styles.body}>Score: {lastTrip.score ?? 'N/A'}</Text>
            <Text style={styles.body}>Distance: {lastTrip.distance_km.toFixed(2)} km</Text>
            <Text style={styles.body}>Duration: {lastTrip.duration_min.toFixed(1)} min</Text>
            {lastTrip.explanation && <Text style={styles.explanation}>{lastTrip.explanation}</Text>}
            <Text style={styles.body}>Events: {lastTrip.events.length}</Text>
            {lastTrip.events.map((e, idx) => (
              <Text key={idx} style={styles.caption}>
                {e.type} {e.peak_g ? `(${e.peak_g.toFixed(2)}g)` : ''}
              </Text>
            ))}
          </Card>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const { colors, radii, space, type } = theme;

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.cream },
  content: { paddingHorizontal: space.xl, paddingTop: space.md, paddingBottom: space.xxl },
  section: { marginTop: space.lg },
  flex1: { flex: 1 },
  eyebrow: { ...type.eyebrow, color: colors.textMuted },
  title: { ...type.title, color: colors.ink },
  display: { ...type.display, color: colors.ink },
  body: { ...type.body, color: colors.ink },
  bodyStrong: { ...type.bodyStrong, color: colors.ink },
  caption: { ...type.caption, color: colors.textMuted },
  explanation: { ...type.body, color: colors.textMuted, fontStyle: 'italic' },
  scoreRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  chip: { borderRadius: radii.chip, paddingHorizontal: space.sm, paddingVertical: 2 },
  switchCard: { minHeight: theme.minSwitchRow },
  switchRow: {
    minHeight: theme.minTouch,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  successStrong: { ...type.bodyStrong, color: colors.success.ink },
  successText: { ...type.body, color: colors.success.ink },
  message: { ...type.body, marginTop: space.sm, padding: space.lg, borderRadius: radii.cardSm },
  retry: { minHeight: theme.minTouch, alignSelf: 'flex-start', justifyContent: 'center' },
  warningHeader: { ...type.bodyStrong, color: colors.warning.ink, marginBottom: space.md },
  tripRow: { marginTop: space.md },
  rowGap: { flexDirection: 'row', gap: space.sm, marginTop: space.md },
  colGap: { flexDirection: 'column', gap: space.sm, marginTop: space.md },
  lastTrip: { marginBottom: space.xl },
});
