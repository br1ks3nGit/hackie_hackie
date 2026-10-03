from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, validator


# --- Auth / Registration ---

class DriverRegisterRequest(BaseModel):
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None


class DriverRegisterResponse(BaseModel):
    driver_id: str
    api_key: str


class ConsentRequest(BaseModel):
    driver_id: str
    version: str


class ConsentResponse(BaseModel):
    status: str
    granted_at: datetime


# --- Trip Ingestion ---

class TripStartResponse(BaseModel):
    trip_id: str


class IMUSample(BaseModel):
    t: int  # epoch ms
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float

    @validator("t")
    def timestamp_must_be_reasonable(cls, v):
        if v < 1000000000000:  # before 2001
            raise ValueError("timestamp must be epoch milliseconds")
        return v


class GPSSample(BaseModel):
    t: int  # epoch ms
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    speed: Optional[float] = Field(None, ge=0)
    heading: Optional[float] = Field(None, ge=0, lt=360)
    accuracy: Optional[float] = Field(None, ge=0)


class TripChunkRequest(BaseModel):
    seq: int = Field(..., ge=0)
    imu: List[IMUSample] = Field(..., min_items=1)
    gps: List[GPSSample] = Field(..., min_items=1)
    car_connected: Optional[bool] = None

    @validator("imu")
    def imu_timestamps_in_order(cls, v):
        for i in range(1, len(v)):
            if v[i].t < v[i - 1].t:
                raise ValueError("IMU timestamps must be in ascending order")
        return v

    @validator("gps")
    def gps_timestamps_in_order(cls, v):
        for i in range(1, len(v)):
            if v[i].t < v[i - 1].t:
                raise ValueError("GPS timestamps must be in ascending order")
        return v


class TripChunkResponse(BaseModel):
    status: str
    received_at: datetime


class TripEndResponse(BaseModel):
    status: str


class TripStatusResponse(BaseModel):
    trip_id: str
    status: str
    failure_reason: Optional[str] = None


# --- Processing Results ---

class EventResponse(BaseModel):
    type: str
    time: datetime
    peak_g: Optional[float]
    lat: Optional[float]
    lon: Optional[float]


class RoutePoint(BaseModel):
    lat: float
    lon: float
    speed: Optional[float]


class TripDetailResponse(BaseModel):
    trip_id: str
    started_at: datetime
    ended_at: Optional[datetime]
    distance_km: float
    duration_min: float
    score: Optional[int]
    confidence: Optional[float]
    tier: Optional[str]
    events: List[EventResponse]
    route: List[RoutePoint]
    explanation: Optional[str]


class TripListItem(BaseModel):
    trip_id: str
    started_at: datetime
    distance_km: float
    score: Optional[int]
    tier: Optional[str]
    trip_type: Optional[str] = None
    needs_confirmation: bool = False
    label_source: Optional[str] = None
    transit_line: Optional[str] = None


# --- Driver Reports ---

class DriverSummaryResponse(BaseModel):
    driver_id: str
    score: int
    confidence: float
    tier: str
    premium_multiplier: float
    trend: str  # improving, stable, worsening
    total_trips_90d: int
    total_distance_km_90d: float


# --- Insurer Reports ---

class InsurerOverviewResponse(BaseModel):
    total_drivers: int
    total_trips_90d: int
    tier_distribution: dict
    average_multiplier: float


class InsurerDriverItem(BaseModel):
    driver_id: str
    score: int
    confidence: float
    tier: str
    premium_multiplier: float
    total_trips_90d: int
    total_distance_km_90d: float


class InsurerDriverDetailResponse(BaseModel):
    driver_id: str
    score: int
    confidence: float
    tier: str
    premium_multiplier: float
    event_rates: dict
    trips: List[TripListItem]
    model_version: str
    passenger_share: float = 0.0
    label_sources: dict = {}
    flagged_for_review: bool = False


class TripLabelRequest(BaseModel):
    trip_type: str = Field(..., pattern="^(driver|passenger)$")


class TripLabelResponse(BaseModel):
    trip_id: str
    trip_type: str
    status: str


# --- Incidents ---

class IncidentCreate(BaseModel):
    type: str = "crash"
    time: datetime
    lat: Optional[float] = None
    lon: Optional[float] = None
    peak_g: Optional[float] = None
    trip_id: Optional[str] = None
    sensor_snapshot: Optional[dict] = None


class IncidentConfirm(BaseModel):
    confirmed: str = Field(..., pattern="^(ok|help_needed|no_response)$")


class IncidentResponse(BaseModel):
    id: int
    type: str
    time: datetime
    lat: Optional[float]
    lon: Optional[float]
    peak_g: Optional[float]
    confirmed: Optional[str]
    created_at: datetime


# --- Admin ---

class ReprocessResponse(BaseModel):
    trip_id: str
    status: str


class DeleteDriverResponse(BaseModel):
    status: str
    deleted_files: int
