import { AccelerometerSample, GyroscopeSample, GPSPoint } from '../types';
import { TripChunkRequest, uploadChunk } from '../api/client';

const TRIP_START_SPEED_MS = 2.0; // ~7 km/h
const TRIP_END_IDLE_S = 180; // 3 minutes below threshold ends trip
const CHUNK_INTERVAL_MS = 60000; // 60 seconds

export class TripDetector {
  private inTrip = false;
  private startedAt: number | null = null;
  private lastMotionAt: number | null = null;
  private tripId: string | null = null;
  private apiKey: string | null = null;

  private accelSamples: AccelerometerSample[] = [];
  private gyroSamples: GyroscopeSample[] = [];
  private gpsPoints: GPSPoint[] = [];

  private chunkSeq = 0;
  private lastChunkUpload = 0;

  private onTripStart?: (tripId: string) => void;
  private onTripEnd?: (tripId: string) => void;
  private onChunkUploaded?: (seq: number) => void;

  constructor(
    callbacks?: {
      onTripStart?: (tripId: string) => void;
      onTripEnd?: (tripId: string) => void;
      onChunkUploaded?: (seq: number) => void;
    }
  ) {
    this.onTripStart = callbacks?.onTripStart;
    this.onTripEnd = callbacks?.onTripEnd;
    this.onChunkUploaded = callbacks?.onChunkUploaded;
  }

  setCredentials(tripId: string, apiKey: string) {
    this.tripId = tripId;
    this.apiKey = apiKey;
  }

  addAccelSample(sample: AccelerometerSample) {
    this.accelSamples.push(sample);
    this._trimSamples(sample.t);
  }

  addGyroSample(sample: GyroscopeSample) {
    this.gyroSamples.push(sample);
    this._trimSamples(sample.t);
  }

  addGpsPoint(point: GPSPoint) {
    this.gpsPoints.push(point);
    this._trimSamples(point.t);

    const speed = point.speed ?? 0;
    const now = point.t * 1000; // convert to ms

    if (speed > TRIP_START_SPEED_MS) {
      this.lastMotionAt = now;
      if (!this.inTrip && this.tripId) {
        this._startTrip(now);
      }
    } else if (this.inTrip && this.lastMotionAt !== null) {
      const idleFor = now - this.lastMotionAt;
      if (idleFor >= TRIP_END_IDLE_S * 1000) {
        this._endTrip();
      }
    }

    // Upload chunk if enough time has passed
    if (this.inTrip && now - this.lastChunkUpload >= CHUNK_INTERVAL_MS) {
      this._uploadChunk();
    }
  }

  async forceStart(tripId: string, apiKey: string) {
    if (!this.inTrip) {
      this.setCredentials(tripId, apiKey);
      const now = Date.now();
      this._startTrip(now);
    }
  }

  async forceEnd() {
    if (this.inTrip) {
      this._endTrip();
    }
  }

  isInTrip(): boolean {
    return this.inTrip;
  }

  getTripId(): string | null {
    return this.tripId;
  }

  private _startTrip(startedAt: number) {
    this.inTrip = true;
    this.startedAt = startedAt;
    this.lastMotionAt = startedAt;
    this.lastChunkUpload = startedAt;
    this.chunkSeq = 0;
    if (this.tripId) {
      this.onTripStart?.(this.tripId);
    }
  }

  private _endTrip() {
    if (!this.inTrip || this.startedAt === null) return;

    // Upload final chunk
    this._uploadChunk();

    this.inTrip = false;
    if (this.tripId) {
      this.onTripEnd?.(this.tripId);
    }

    this.startedAt = null;
    this.lastMotionAt = null;
    this.tripId = null;
    this.apiKey = null;
  }

  private async _uploadChunk() {
    if (!this.tripId || !this.apiKey || this.accelSamples.length === 0) return;

    const chunk: TripChunkRequest = {
      seq: this.chunkSeq,
      imu: this._mergeImuSamples(),
      gps: this.gpsPoints.map(p => ({
        t: Math.round(p.t * 1000),
        lat: p.lat,
        lon: p.lng,
        speed: p.speed,
        accuracy: p.accuracy,
      })),
    };

    try {
      await uploadChunk(this.tripId, chunk, this.apiKey);
      this.onChunkUploaded?.(this.chunkSeq);
      this.chunkSeq++;
      this.lastChunkUpload = Date.now();

      // Clear uploaded samples
      this.accelSamples = [];
      this.gyroSamples = [];
      this.gpsPoints = [];
    } catch (err) {
      console.warn('Failed to upload chunk, will retry', err);
      // Keep samples for retry
    }
  }

  private _mergeImuSamples(): Array<{ t: number; ax: number; ay: number; az: number; gx: number; gy: number; gz: number }> {
    // Merge accelerometer and gyroscope samples by timestamp
    // For simplicity, use accelerometer timestamps and interpolate gyro
    return this.accelSamples.map(a => {
      const nearestGyro = this.gyroSamples.reduce((prev, curr) =>
        Math.abs(curr.t - a.t) < Math.abs(prev.t - a.t) ? curr : prev
      , this.gyroSamples[0] || { t: 0, x: 0, y: 0, z: 0 });

      return {
        t: Math.round(a.t * 1000),
        ax: a.x,
        ay: a.y,
        az: a.z,
        gx: nearestGyro.x,
        gy: nearestGyro.y,
        gz: nearestGyro.z,
      };
    });
  }

  private _trimSamples(currentTime: number) {
    // Keep only the last 10 minutes of samples to bound memory
    const cutoff = currentTime - 600;
    if (this.accelSamples.length > 10000) {
      this.accelSamples = this.accelSamples.filter(s => s.t >= cutoff);
    }
    if (this.gyroSamples.length > 10000) {
      this.gyroSamples = this.gyroSamples.filter(s => s.t >= cutoff);
    }
    if (this.gpsPoints.length > 2000) {
      this.gpsPoints = this.gpsPoints.filter(p => p.t >= cutoff);
    }
  }
}
