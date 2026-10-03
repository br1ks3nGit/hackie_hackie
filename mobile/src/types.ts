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
