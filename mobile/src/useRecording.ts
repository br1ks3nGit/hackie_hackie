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

// Ends the trip and polls until processed (up to ~60 s). False if cancelled (unmounted).
async function endAndPoll(tripId: string, key: string, cancelled: () => boolean): Promise<boolean> {
  await endTrip(tripId, key);
  let status = 'processing';
  for (let i = 0; i < STATUS_POLL_MAX && status === 'processing'; i++) {
    if (cancelled()) return false;
    await new Promise((resolve) => setTimeout(resolve, STATUS_POLL_MS));
    if (cancelled()) return false;
    status = (await getTripStatus(tripId, key)).status;
  }
  return !cancelled();
}

// Stops sensors and drops the detector on unmount (e.g. after account deletion); the returned
// ref turns true so in-flight status polling stops.
function useUnmountGuard(detectorRef: { current: TripDetector | null }) {
  const cancelledRef = useRef(false);
  useEffect(() => {
    cancelledRef.current = false;
    return () => {
      cancelledRef.current = true;
      stopSensors();
      detectorRef.current = null;
    };
  }, [detectorRef]);
  return cancelledRef;
}

// Count of stop/end/poll operations in flight; `finishing` is pending > 0
function usePending() {
  const [finishing, setFinishing] = useState(false);
  const pendingRef = useRef(0);
  const trackPending = (delta: number) => {
    pendingRef.current += delta;
    setFinishing(pendingRef.current > 0);
  };
  return { finishing, trackPending };
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
  const [starting, setStarting] = useState(false);
  const { finishing, trackPending } = usePending();
  const detectorRef = useRef<TripDetector | null>(null);
  const { drivingMode, drivingModeRef, changeDrivingMode } = useDrivingMode();

  const cancelledRef = useUnmountGuard(detectorRef);

  const finishTrip = async (tripId: string, key: string) => {
    trackPending(1);
    try {
      const done = await endAndPoll(tripId, key, () => cancelledRef.current);
      if (done) onProcessedRef.current();
    } catch (err) {
      console.error('Failed to end trip', err);
    } finally {
      trackPending(-1);
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
      trackPending(1);
      try {
        await detectorRef.current?.forceEnd();
      } finally {
        trackPending(-1);
      }
      return;
    }
    setStarting(true);

    if (!apiKey) {
      setStarting(false);
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
    } finally {
      setStarting(false);
    }
  };

  return {
    recording,
    inTrip,
    currentTripId,
    chunkCount,
    busy: starting || recording || finishing,
    drivingMode,
    changeDrivingMode,
    toggleRecording,
  };
}
