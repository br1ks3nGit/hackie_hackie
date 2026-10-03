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

// GPS speed sample: coordinates are read by the OS but never copied into the app.
export interface SpeedSample {
  t: number;
  speed?: number;
  accuracy?: number;
}
