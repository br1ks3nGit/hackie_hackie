import { API_BASE_URL } from '../config';

const API_BASE = `${API_BASE_URL}/v1`;

export interface DriverRegisterResponse {
  driver_id: string;
  api_key: string;
}

export interface TripStartResponse {
  trip_id: string;
}

export interface TripChunkRequest {
  seq: number;
  car_connected?: boolean | null;
  imu: Array<{
    t: number;
    ax: number;
    ay: number;
    az: number;
    gx: number;
    gy: number;
    gz: number;
  }>;
  gps: Array<{
    t: number;
    speed?: number;
    heading?: number;
    accuracy?: number;
  }>;
}

export interface TripStatusResponse {
  trip_id: string;
  status: string;
  failure_reason?: string;
}

export interface DriverSummaryResponse {
  driver_id: string;
  score: number;
  confidence: number;
  tier: string;
  premium_multiplier: number;
  trend: string;
  total_trips_90d: number;
  total_distance_km_90d: number;
}

export type TripType = 'driver' | 'passenger' | 'transit' | 'unknown';
export type LabelSource = 'bluetooth' | 'rules' | 'user';
export type Tier = 'A' | 'B' | 'C' | 'D' | 'E';

export interface TripListItem {
  trip_id: string;
  started_at: string;
  distance_km: number;
  score: number | null;
  tier: Tier | null;
  trip_type: TripType | null;
  needs_confirmation: boolean;
  label_source: LabelSource | null;
  transit_line: string | null;
}

export interface TripLabelResponse {
  trip_id: string;
  trip_type: 'driver' | 'passenger';
  status: 'added_to_score' | 'removed_from_score' | 'relabelled';
}

export interface DeleteDriverResponse {
  status: 'deleted';
  deleted_files: number;
}

export interface EventResponse {
  type: string;
  time: string;
  peak_g?: number;
}

export interface TripDetailResponse {
  trip_id: string;
  started_at: string;
  ended_at: string | null;
  distance_km: number;
  duration_min: number;
  score: number | null;
  confidence: number | null;
  tier: Tier | null;
  events: EventResponse[];
  explanation: string | null;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, text: string) {
    super(`API error ${status}: ${text}`);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit, apiKey?: string): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init?.headers as Record<string, string> || {}),
  };

  if (apiKey) {
    headers['X-API-Key'] = apiKey;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(response.status, text);
  }

  return response.json() as Promise<T>;
}

export async function registerDriver(): Promise<DriverRegisterResponse> {
  return request('/drivers/register', { method: 'POST' });
}

export async function giveConsent(apiKey: string, version: string = '1.0'): Promise<void> {
  await request('/consent', {
    method: 'POST',
    body: JSON.stringify({ version }),
  }, apiKey);
}

export async function startTrip(apiKey: string): Promise<TripStartResponse> {
  return request('/trips/start', { method: 'POST' }, apiKey);
}

export async function uploadChunk(
  tripId: string,
  chunk: TripChunkRequest,
  apiKey: string,
): Promise<void> {
  await request(`/trips/${tripId}/chunks`, {
    method: 'POST',
    body: JSON.stringify(chunk),
  }, apiKey);
}

export async function endTrip(tripId: string, apiKey: string): Promise<void> {
  await request(`/trips/${tripId}/end`, { method: 'POST' }, apiKey);
}

export async function getTripStatus(tripId: string, apiKey: string): Promise<TripStatusResponse> {
  return request(`/trips/${tripId}/status`, {}, apiKey);
}

export async function getDriverSummary(apiKey: string): Promise<DriverSummaryResponse> {
  return request('/me/summary', {}, apiKey);
}

export async function getMyTrips(
  apiKey: string,
  limit: number = 50,
  offset: number = 0,
): Promise<TripListItem[]> {
  return request(`/me/trips?limit=${limit}&offset=${offset}`, {}, apiKey);
}

export async function getTripDetail(tripId: string, apiKey: string): Promise<TripDetailResponse> {
  return request(`/me/trips/${tripId}`, {}, apiKey);
}

export async function labelTrip(
  tripId: string,
  tripType: 'driver' | 'passenger',
  apiKey: string,
): Promise<TripLabelResponse> {
  return request(`/me/trips/${tripId}/label`, {
    method: 'POST',
    body: JSON.stringify({ trip_type: tripType }),
  }, apiKey);
}

export async function deleteMe(apiKey: string): Promise<DeleteDriverResponse> {
  return request('/me', { method: 'DELETE' }, apiKey);
}
