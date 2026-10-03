import './global.css';
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
import { SafeAreaView } from 'react-native-safe-area-context';
import { SWITCH_TRACK_OFF, SWITCH_TRACK_ON } from './src/tokens';
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

// Literal class names so NativeWind can see them at build time
const TIER_CHIP: Record<string, string> = {
  A: 'bg-tier-a-soft',
  B: 'bg-tier-b-soft',
  C: 'bg-tier-c-soft',
  D: 'bg-tier-d-soft',
  E: 'bg-tier-e-soft',
};
const TIER_CHIP_TEXT: Record<string, string> = {
  A: 'text-tier-a-ink',
  B: 'text-tier-b-ink',
  C: 'text-tier-c-ink',
  D: 'text-tier-d-ink',
  E: 'text-tier-e-ink',
};

const PRIMARY_BTN =
  'min-h-11 items-center justify-center rounded-md bg-primary px-3 active:bg-primary-active';
const SECONDARY_BTN =
  'min-h-11 items-center justify-center rounded-md border border-primary bg-surface ' +
  'px-3 active:bg-surface-muted';

const STORAGE_KEYS = {
  DRIVER_ID: 'drivescore:driver_id',
  API_KEY: 'drivescore:api_key',
  DRIVING_MODE: 'drivescore:driving_mode',
};

export default function App() {
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
  // flex-1 only in a row: in a stacked column it would collapse the buttons to min height
  const btnFlex = stackButtons ? '' : 'flex-1';

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

  const tierKey = summary?.tier.toUpperCase() ?? '';
  const messageText = labelError ?? loadError ?? labelMessage ?? '';
  const messageClass = labelError || loadError
    ? 'mt-2 rounded-lg bg-danger-soft p-4 text-base text-danger-ink'
    : messageText
      ? 'mt-2 rounded-lg bg-success-soft p-4 text-base text-success-ink'
      : '';
  const disabledClass = labelling ? 'opacity-50' : '';

  return (
    <SafeAreaView className="flex-1 bg-surface">
    <ScrollView className="flex-1 px-5 pt-4">
      <Text className="mb-2 text-3xl font-bold text-text">DriveScore</Text>

      {driverId && (
        <Text className="mb-4 text-sm text-text-muted">Driver: {driverId.substring(0, 12)}...</Text>
      )}

      {summary && (
        <View className="mb-4 gap-1 rounded-lg bg-surface-muted p-4">
          <Text className="text-sm text-text-muted">Your Score</Text>
          <View className="flex-row items-center gap-3">
            <Text className="text-5xl font-bold text-text">{summary.score}</Text>
            <View
              className={`rounded-sm px-2 py-0.5 ${TIER_CHIP[tierKey] ?? 'bg-border'}`}
              accessible
              accessibilityLabel={`Tier ${summary.tier}`}
            >
              <Text className={`text-xs font-semibold ${TIER_CHIP_TEXT[tierKey] ?? 'text-text'}`}>
                {summary.tier}
              </Text>
            </View>
          </View>
          <Text className="text-base text-text">
            Premium Multiplier: {summary.premium_multiplier}x
          </Text>
          <Text className="text-base text-text">Trend: {summary.trend}</Text>
          <Text className="text-base text-text">Trips (90d): {summary.total_trips_90d}</Text>
        </View>
      )}

      <Pressable
        className="min-h-12 flex-row items-center justify-between py-2"
        onPress={() => changeDrivingMode(!drivingMode)}
        accessibilityRole="switch"
        accessibilityState={{ checked: drivingMode }}
        accessibilityLabel="I'm driving"
      >
        <Text className="text-base font-semibold text-text">
          I'm driving: {drivingMode ? 'On' : 'Off'}
        </Text>
        <Switch
          value={drivingMode}
          onValueChange={changeDrivingMode}
          accessible={false}
          trackColor={{ true: SWITCH_TRACK_ON, false: SWITCH_TRACK_OFF }}
        />
      </Pressable>
      <Text className="mb-4 text-sm text-text-muted">
        Turn on when you are the driver. Trips recorded while off do not count toward your score
        unless you confirm them later.
      </Text>

      <Pressable
        className={`min-h-11 items-center justify-center rounded-md px-3 ${
          recording ? 'bg-danger active:bg-danger-ink' : 'bg-primary active:bg-primary-active'
        }`}
        onPress={toggleRecording}
        accessibilityRole="button"
        accessibilityLabel={recording ? 'Stop Recording' : 'Start Recording'}
      >
        <Text className="text-base font-semibold text-primary-fg">
          {recording ? 'Stop Recording' : 'Start Recording'}
        </Text>
      </Pressable>

      {recording && (
        <View className="mt-5 rounded-lg bg-success-soft p-4">
          <Text className="text-base font-semibold text-success-ink">Recording trip</Text>
          <Text className="text-base text-success-ink">
            Status: {inTrip ? 'In trip' : 'Recording (idle)'}
          </Text>
          <Text className="text-base text-success-ink">Driving: {drivingMode ? 'Yes' : 'No'}</Text>
          <Text className="text-base text-success-ink">Chunks uploaded: {chunkCount}</Text>
          {currentTripId && (
            <Text className="text-base text-success-ink">
              Trip: {currentTripId.substring(0, 16)}...
            </Text>
          )}
        </View>
      )}

      <Text className={messageClass} accessibilityLiveRegion="polite">
        {messageText}
      </Text>
      {loadError && apiKey && (
        <Pressable
          className="min-h-11 self-start justify-center px-3"
          onPress={() => refreshToConfirm(apiKey)}
          accessibilityRole="button"
          accessibilityLabel="Retry loading trips to confirm"
        >
          <Text className="text-base font-semibold text-primary">Retry</Text>
        </Pressable>
      )}

      {toConfirm.length > 0 && (
        <View className="mt-5 gap-3 rounded-lg bg-warning-soft p-4">
          <Text className="text-base font-semibold text-warning-ink" accessibilityRole="header">
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
              <View key={trip.trip_id} className="gap-3 rounded-lg bg-surface p-4">
                <Text className="text-base font-semibold text-text">
                  {date} {time}
                  {'\n'}
                  {trip.distance_km.toFixed(1)} km
                </Text>
                <View className={`gap-2 ${stackButtons ? 'flex-col' : 'flex-row'}`}>
                  <Pressable
                    className={`${PRIMARY_BTN} ${btnFlex} ${disabledClass}`}
                    disabled={labelling}
                    onPress={() => confirmTrip(trip, 'driver')}
                    accessibilityRole="button"
                    accessibilityLabel={`I was driving, trip on ${date} at ${time}`}
                    accessibilityState={{ disabled: labelling }}
                  >
                    <Text className="text-center text-base font-semibold text-primary-fg">
                      I was driving
                    </Text>
                  </Pressable>
                  <Pressable
                    className={`${SECONDARY_BTN} ${btnFlex} ${disabledClass}`}
                    disabled={labelling}
                    onPress={() => confirmTrip(trip, 'passenger')}
                    accessibilityRole="button"
                    accessibilityLabel={`I was a passenger, trip on ${date} at ${time}`}
                    accessibilityState={{ disabled: labelling }}
                  >
                    <Text className="text-center text-base font-semibold text-primary">
                      I was a passenger
                    </Text>
                  </Pressable>
                </View>
              </View>
            );
          })}
        </View>
      )}

      {lastTrip && (
        <View className="mb-10 mt-5 gap-1 rounded-lg bg-surface-muted p-4">
          <Text className="text-base font-semibold text-text">Last Trip</Text>
          <Text className="text-base text-text">Score: {lastTrip.score ?? 'N/A'}</Text>
          <Text className="text-base text-text">
            Distance: {lastTrip.distance_km.toFixed(2)} km
          </Text>
          <Text className="text-base text-text">
            Duration: {lastTrip.duration_min.toFixed(1)} min
          </Text>
          {lastTrip.explanation && (
            <Text className="text-base italic text-text-muted">{lastTrip.explanation}</Text>
          )}
          <Text className="text-base text-text">Events: {lastTrip.events.length}</Text>
          {lastTrip.events.map((e, idx) => (
            <Text key={idx} className="ml-2 text-sm text-text-muted">
              {e.type} {e.peak_g ? `(${e.peak_g.toFixed(2)}g)` : ''}
            </Text>
          ))}
        </View>
      )}
    </ScrollView>
    </SafeAreaView>
  );
}
