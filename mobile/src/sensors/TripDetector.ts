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
  private uploadInFlight: Promise<boolean> | null = null;

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
        void this._endTrip();
      }
    }

    // Upload chunk if enough time has passed
    if (this.inTrip && !this.uploadInFlight && now - this.lastChunkUpload >= CHUNK_INTERVAL_MS) {
      void this._uploadChunk();
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
      await this._endTrip();
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

  private async _endTrip() {
    if (!this.inTrip || this.startedAt === null) return;

    // Upload the final chunk (with retries) BEFORE ending the trip on the
    // server: /end is only sent once the last chunk is acknowledged.
    await this._uploadFinalChunkWithRetry(3);

    this.inTrip = false;
    const tripId = this.tripId;

    this.startedAt = null;
    this.lastMotionAt = null;
    this.tripId = null;
    this.apiKey = null;

    if (tripId) {
      this.onTripEnd?.(tripId);
    }
  }

  private async _uploadFinalChunkWithRetry(maxAttempts: number): Promise<void> {
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      const ok = await this._uploadChunk();
      if (ok) return;
      console.warn(`Final chunk upload attempt ${attempt}/${maxAttempts} failed`);
      if (attempt < maxAttempts) {
        // Small backoff before retrying
        await new Promise(resolve => setTimeout(resolve, 500 * attempt));
      }
    }
    console.error('Final chunk upload failed after all retries; ending trip without it');
  }

  // Uploads are serialized: a new upload waits for the one in flight, so two
  // uploads never share a seq and samples are never cleared twice
  private _uploadChunk(): Promise<boolean> {
    const run = this.uploadInFlight ?? Promise.resolve(true);
    const next = run.then(() => this._sendChunk());
    this.uploadInFlight = next;
    void next.finally(() => {
      if (this.uploadInFlight === next) this.uploadInFlight = null;
    });
    return next;
  }

  private async _sendChunk(): Promise<boolean> {
    if (!this.tripId || !this.apiKey || this.accelSamples.length === 0) return true;

    // Take the buffered samples now; samples that arrive during the upload go
    // into fresh buffers and are sent with the next chunk
    const accel = this.accelSamples;
    const gyro = this.gyroSamples;
    const gpsPoints = this.gpsPoints;
    this.accelSamples = [];
    this.gyroSamples = [];
    this.gpsPoints = [];
    const seq = this.chunkSeq;

    const chunk: TripChunkRequest = {
      seq,
      imu: this._mergeImuSamples(accel, gyro),
      gps: gpsPoints.map(p => ({
        t: Math.round(p.t * 1000),
        lat: p.lat,
        lon: p.lng,
        speed: p.speed,
        accuracy: p.accuracy,
      })),
    };

    try {
      await uploadChunk(this.tripId, chunk, this.apiKey);
      this.onChunkUploaded?.(seq);
      this.chunkSeq++;
      this.lastChunkUpload = Date.now();
      return true;
    } catch (err) {
      console.warn('Failed to upload chunk, will retry', err);
      // Put the samples back in front of anything recorded since
      this.accelSamples = accel.concat(this.accelSamples);
      this.gyroSamples = gyro.concat(this.gyroSamples);
      this.gpsPoints = gpsPoints.concat(this.gpsPoints);
      return false;
    }
  }

  private _mergeImuSamples(
    accel: AccelerometerSample[],
    gyro: GyroscopeSample[],
  ): Array<{ t: number; ax: number; ay: number; az: number; gx: number; gy: number; gz: number }> {
    // Pair each accelerometer sample with the nearest gyro sample. Both arrays
    // are in time order, so one forward pointer is enough (linear time).
    let j = 0;
    return accel.map(a => {
      while (j + 1 < gyro.length && Math.abs(gyro[j + 1].t - a.t) <= Math.abs(gyro[j].t - a.t)) {
        j++;
      }
      const g = gyro[j] || { t: 0, x: 0, y: 0, z: 0 };
      return {
        t: Math.round(a.t * 1000),
        ax: a.x,
        ay: a.y,
        az: a.z,
        gx: g.x,
        gy: g.y,
        gz: g.z,
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
