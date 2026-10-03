import { useEffect, useRef, useState } from 'react';
import { Alert } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useLanguage } from './i18n';
import { TripDetector } from './sensors/TripDetector';
import { startSensors, stopSensors } from './sensors/SensorManager';
import { startTrip, endTrip, getTripStatus } from './api/client';

export const DRIVING_MODE_KEY = 'drivescore:driving_mode';

const STATUS_POLL_MS = 2000;
const STATUS_POLL_MAX = 30;

// Driving-mode toggle persisted in AsyncStorage; the ref is read by TripDetector.
function useDrivingMode() {
  const [drivingMode, setDrivingMode] = useState(false);
  // Read by TripDetector at chunk-build time, so flipping mid-trip applies to the next chunk
  const drivingModeRef = useRef(false);
  // Set once the user toggles, so a late AsyncStorage load cannot overwrite their choice
  const touchedRef = useRef(false);

  useEffect(() => {
    AsyncStorage.getItem(DRIVING_MODE_KEY)
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
    AsyncStorage.setItem(DRIVING_MODE_KEY, String(value)).catch((err) =>
      console.warn('Could not save driving mode', err),
    );
  };

  return { drivingMode, drivingModeRef, changeDrivingMode };
}

// Recording state: detector refs, start/stop, chunk upload, end + status polling, driving mode.
export function useRecording(apiKey: string | null, onTripProcessed: () => void) {
  const { t } = useLanguage();
  const tRef = useRef(t);
  tRef.current = t;
  const onProcessedRef = useRef(onTripProcessed);
  onProcessedRef.current = onTripProcessed;
  const [recording, setRecording] = useState(false);
  const [inTrip, setInTrip] = useState(false);
  const [currentTripId, setCurrentTripId] = useState<string | null>(null);
  const [chunkCount, setChunkCount] = useState(0);

  const detectorRef = useRef<TripDetector | null>(null);
  const { drivingMode, drivingModeRef, changeDrivingMode } = useDrivingMode();

  const finishTrip = async (tripId: string, key: string) => {
    try {
      await endTrip(tripId, key);
      // Poll until the backend finishes processing (up to ~60 s)
      let status = 'processing';
      for (let i = 0; i < STATUS_POLL_MAX && status === 'processing'; i++) {
        await new Promise((resolve) => setTimeout(resolve, STATUS_POLL_MS));
        status = (await getTripStatus(tripId, key)).status;
      }
      onProcessedRef.current();
    } catch (err) {
      console.error('Failed to end trip', err);
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
        if (apiKey) await finishTrip(tripId, apiKey);
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
      // forceEnd awaits the final chunk upload (with retries); onTripEnd -
      // which sends /end - fires only after the last chunk is acknowledged
      await detectorRef.current?.forceEnd();
      return;
    }

    if (!apiKey) {
      Alert.alert(t('notReadyTitle'), t('notReadyBody'));
      return;
    }

    try {
      setupDetector();
      const tripResponse = await startTrip(apiKey);
      await detectorRef.current?.forceStart(tripResponse.trip_id, apiKey);
      await startSensors(
        (sample) => detectorRef.current?.addAccelSample(sample),
        (sample) => detectorRef.current?.addGyroSample(sample),
        (point) => detectorRef.current?.addGpsPoint(point),
      );
      setRecording(true);
      setChunkCount(0);
    } catch (err) {
      Alert.alert(t('errorTitle'), t('startError'));
      console.error(err);
    }
  };

  return {
    recording,
    inTrip,
    currentTripId,
    chunkCount,
    drivingMode,
    changeDrivingMode,
    toggleRecording,
  };
}
