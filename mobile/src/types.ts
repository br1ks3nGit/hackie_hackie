export interface AccelerometerSample {
  t: number;
  x: number;
  y: number;
  z: number;
}

export interface GyroscopeSample {
  t: number;
  x: number;
  y: number;
  z: number;
}

export interface GPSPoint {
  t: number;
  lat: number;
  lng: number;
  speed?: number;
  accuracy?: number;
}

export interface TripMetadata {
  distance_m?: number;
  duration_s?: number;
  phone_model?: string;
  app_version?: string;
}

export interface TripUpload {
  trip_id: string;
  user_id: string;
  device_id?: string;
  started_at: string;
  ended_at: string;
  accelerometer: AccelerometerSample[];
  gyroscope: GyroscopeSample[];
  gps: GPSPoint[];
  metadata: TripMetadata;
}

export interface Event {
  type: 'hard_brake' | 'hard_accel' | 'sharp_turn' | 'crash';
  t: number;
  severity: number;
  lat?: number;
  lng?: number;
}

export interface TripScore {
  trip_id: string;
  user_id: string;
  status: 'scored' | 'needs_review' | 'rejected';
  is_outlier: boolean;
  risk_score: number;
  events: Event[];
  factors: Record<string, number>;
}

export interface DriverSummary {
  user_id: string;
  overall_score: number;
  total_trips: number;
  total_distance_m: number;
  recent_trips: TripScore[];
}
