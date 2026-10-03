import AsyncStorage from '@react-native-async-storage/async-storage';
import { TripUpload, TripScore } from '../types';

const PENDING_TRIPS_KEY = 'drivescore:pending_trips';
const SCORE_CACHE_KEY = 'drivescore:score_cache';

export async function savePendingTrip(trip: TripUpload): Promise<void> {
  const existing = await getPendingTrips();
  existing.push(trip);
  await AsyncStorage.setItem(PENDING_TRIPS_KEY, JSON.stringify(existing));
}

export async function getPendingTrips(): Promise<TripUpload[]> {
  const raw = await AsyncStorage.getItem(PENDING_TRIPS_KEY);
  if (!raw) return [];
  try {
    return JSON.parse(raw) as TripUpload[];
  } catch {
    return [];
  }
}

export async function clearPendingTrip(tripId: string): Promise<void> {
  const existing = await getPendingTrips();
  const filtered = existing.filter(t => t.trip_id !== tripId);
  await AsyncStorage.setItem(PENDING_TRIPS_KEY, JSON.stringify(filtered));
}

export async function cacheScore(score: TripScore): Promise<void> {
  const raw = await AsyncStorage.getItem(SCORE_CACHE_KEY);
  let cache: Record<string, TripScore> = {};
  if (raw) {
    try {
      cache = JSON.parse(raw);
    } catch {
      cache = {};
    }
  }
  cache[score.trip_id] = score;
  await AsyncStorage.setItem(SCORE_CACHE_KEY, JSON.stringify(cache));
}

export async function getCachedScore(tripId: string): Promise<TripScore | null> {
  const raw = await AsyncStorage.getItem(SCORE_CACHE_KEY);
  if (!raw) return null;
  try {
    const cache = JSON.parse(raw) as Record<string, TripScore>;
    return cache[tripId] || null;
  } catch {
    return null;
  }
}
