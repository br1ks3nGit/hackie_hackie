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

// Speed only: coordinates are read by the OS but never copied into the app.
export interface GPSPoint {
  t: number;
  speed?: number;
  accuracy?: number;
}
