import React, { useEffect, useRef, useState } from 'react';
import { View, Text, Button, Switch, Pressable, StyleSheet, Alert, ScrollView } from 'react-native';
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
  DriverSummaryResponse,
  TripDetailResponse,
} from './src/api/client';
import AsyncStorage from '@react-native-async-storage/async-storage';

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

  const detectorRef = useRef<TripDetector | null>(null);
  // Read by TripDetector at chunk-build time, so flipping mid-trip applies to the next chunk
  const drivingModeRef = useRef(false);
  // Set once the user toggles, so a late AsyncStorage load cannot overwrite their choice
  const touchedRef = useRef(false);

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

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>DriveScore</Text>

      {driverId && (
        <Text style={styles.subtitle}>Driver: {driverId.substring(0, 12)}...</Text>
      )}

      {summary && (
        <View style={styles.scoreBox}>
          <Text style={styles.scoreTitle}>Your Score</Text>
          <Text style={styles.scoreValue}>{summary.score}</Text>
          <Text>Tier: {summary.tier}</Text>
          <Text>Premium Multiplier: {summary.premium_multiplier}x</Text>
          <Text>Trend: {summary.trend}</Text>
          <Text>Trips (90d): {summary.total_trips_90d}</Text>
        </View>
      )}

      <Pressable
        style={styles.drivingRow}
        onPress={() => changeDrivingMode(!drivingMode)}
        accessibilityRole="switch"
        accessibilityState={{ checked: drivingMode }}
        accessibilityLabel="I'm driving"
      >
        <Text style={styles.drivingLabel}>I'm driving: {drivingMode ? 'On' : 'Off'}</Text>
        <Switch value={drivingMode} onValueChange={changeDrivingMode} accessible={false} />
      </Pressable>
      <Text style={styles.drivingHint}>
        Turn on when you are the driver. Trips recorded while off do not count toward your score
        unless you confirm them later.
      </Text>

      <Button
        title={recording ? 'Stop Recording' : 'Start Recording'}
        onPress={toggleRecording}
        color={recording ? '#FF3B30' : '#34C759'}
      />

      {recording && (
        <View style={styles.statusBox}>
          <Text>Status: {inTrip ? 'In trip' : 'Recording (idle)'}</Text>
          <Text>Driving: {drivingMode ? 'Yes' : 'No'}</Text>
          <Text>Chunks uploaded: {chunkCount}</Text>
          {currentTripId && <Text>Trip: {currentTripId.substring(0, 16)}...</Text>}
        </View>
      )}

      {lastTrip && (
        <View style={styles.tripBox}>
          <Text style={styles.tripTitle}>Last Trip</Text>
          <Text>Score: {lastTrip.score ?? 'N/A'}</Text>
          <Text>Distance: {lastTrip.distance_km.toFixed(2)} km</Text>
          <Text>Duration: {lastTrip.duration_min.toFixed(1)} min</Text>
          {lastTrip.explanation && <Text style={styles.explanation}>{lastTrip.explanation}</Text>}
          <Text>Events: {lastTrip.events.length}</Text>
          {lastTrip.events.map((e, idx) => (
            <Text key={idx} style={styles.eventText}>
              {e.type} {e.peak_g ? `(${e.peak_g.toFixed(2)}g)` : ''}
            </Text>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingTop: 60,
    paddingHorizontal: 20,
    backgroundColor: '#fff',
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    marginBottom: 10,
  },
  subtitle: {
    fontSize: 14,
    color: '#666',
    marginBottom: 20,
  },
  drivingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 48,
    marginBottom: 4,
  },
  drivingLabel: {
    fontSize: 16,
    fontWeight: '600',
  },
  drivingHint: {
    fontSize: 13,
    color: '#666',
    marginBottom: 16,
  },
  scoreBox: {
    padding: 15,
    backgroundColor: '#f2f2f7',
    borderRadius: 10,
    marginBottom: 20,
  },
  scoreTitle: {
    fontWeight: 'bold',
    fontSize: 18,
    marginBottom: 5,
  },
  scoreValue: {
    fontSize: 48,
    fontWeight: 'bold',
    color: '#007AFF',
  },
  statusBox: {
    marginTop: 20,
    padding: 15,
    backgroundColor: '#e5f5e5',
    borderRadius: 10,
  },
  tripBox: {
    marginTop: 20,
    padding: 15,
    backgroundColor: '#f2f2f7',
    borderRadius: 10,
    marginBottom: 40,
  },
  tripTitle: {
    fontWeight: 'bold',
    fontSize: 16,
    marginBottom: 5,
  },
  explanation: {
    fontStyle: 'italic',
    color: '#555',
    marginTop: 5,
  },
  eventText: {
    fontSize: 12,
    color: '#555',
    marginLeft: 10,
  },
});
