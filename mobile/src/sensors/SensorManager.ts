import { Accelerometer, Gyroscope } from 'expo-sensors';
import * as Location from 'expo-location';
import { AccelerometerSample, GyroscopeSample, GPSPoint } from '../types';

type AccelCallback = (sample: AccelerometerSample) => void;
type GyroCallback = (sample: GyroscopeSample) => void;
type GpsCallback = (point: GPSPoint) => void;

let accelSubscription: any = null;
let gyroSubscription: any = null;
let locationSubscription: Location.LocationSubscription | null = null;

export async function startSensors(
  onAccel: AccelCallback,
  onGyro: GyroCallback,
  onGps: GpsCallback
): Promise<void> {
  const { status } = await Location.requestForegroundPermissionsAsync();
  if (status !== 'granted') {
    throw new Error('Location permission not granted');
  }

  await Location.requestBackgroundPermissionsAsync();

  Accelerometer.setUpdateInterval(20); // 50 Hz
  Gyroscope.setUpdateInterval(20); // 50 Hz

  accelSubscription = Accelerometer.addListener(({ x, y, z }) => {
    onAccel({ t: Date.now() / 1000, x, y, z });
  });

  gyroSubscription = Gyroscope.addListener(({ x, y, z }) => {
    onGyro({ t: Date.now() / 1000, x, y, z });
  });

  locationSubscription = await Location.watchPositionAsync(
    {
      accuracy: Location.Accuracy.BestForNavigation,
      timeInterval: 1000,
      // 0 = keep a 1 Hz fix while stopped; a distance filter leaves GPS gaps
      // at red lights that fail the backend's 30 s max-gap quality check
      distanceInterval: 0,
      mayShowUserSettingsDialog: true,
    },
    (location) => {
      onGps({
        t: location.timestamp / 1000,
        lat: location.coords.latitude,
        lng: location.coords.longitude,
        speed: location.coords.speed ?? undefined,
        accuracy: location.coords.accuracy ?? undefined,
      });
    }
  );
}

export function stopSensors(): void {
  if (accelSubscription) {
    accelSubscription.remove();
    accelSubscription = null;
  }
  if (gyroSubscription) {
    gyroSubscription.remove();
    gyroSubscription = null;
  }
  if (locationSubscription) {
    locationSubscription.remove();
    locationSubscription = null;
  }
}
