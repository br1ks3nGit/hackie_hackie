from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.values import (
    EventType,
    IncidentConfirmation,
    LabelSource,
    Tier,
    Trend,
    TripStatus,
    TripType,
)

# Reused example values
_TS = "2026-01-02T03:04:05Z"
_EPOCH_MS = 1767225600000
_TRIP_ID = "trp_1a2b3c"
_DRIVER_ID = "drv_8f3a2c"

# --- Auth / Registration ---


class DriverRegisterRequest(BaseModel):
    """Request body of POST /v1/drivers/register."""

    emergency_contact_name: str | None = Field(
        None, description="Name of the emergency contact.", examples=["Alex Chan"]
    )
    emergency_contact_phone: str | None = Field(
        None, description="Phone number of the emergency contact.", examples=["+85291234567"]
    )


class DriverRegisterResponse(BaseModel):
    """Response of POST /v1/drivers/register."""

    driver_id: str = Field(description="Server-generated driver id.", examples=[_DRIVER_ID])
    api_key: str = Field(
        description="Secret key for the X-API-Key header. Shown once, stored only as a hash.",
        examples=["dk_live_example"],
    )


class ConsentRequest(BaseModel):
    """Request body of POST /v1/consent."""

    version: str = Field(description="Version of the consent text accepted.", examples=["1.0"])


class ConsentResponse(BaseModel):
    """Response of POST /v1/consent."""

    status: Literal["consent_recorded"] = Field(description="Always consent_recorded.")
    granted_at: datetime = Field(description="When consent was recorded (UTC).", examples=[_TS])


# --- Trip Ingestion ---


class TripStartResponse(BaseModel):
    """Response of POST /v1/trips/start."""

    trip_id: str = Field(description="Id of the new trip (status uploading).", examples=[_TRIP_ID])


class IMUSample(BaseModel):
    """One inertial sensor reading."""

    t: int = Field(description="Sample time, epoch milliseconds (UTC).", examples=[_EPOCH_MS])
    ax: float = Field(description="Accelerometer x, g.", examples=[0.02])
    ay: float = Field(description="Accelerometer y, g.", examples=[-0.01])
    az: float = Field(description="Accelerometer z, g.", examples=[0.98])
    gx: float = Field(description="Gyroscope x, rad/s.", examples=[0.001])
    gy: float = Field(description="Gyroscope y, rad/s.", examples=[0.0])
    gz: float = Field(description="Gyroscope z, rad/s.", examples=[-0.002])

    @field_validator("t")
    @classmethod
    def timestamp_must_be_reasonable(cls, v: Any) -> Any:
        if v < 1000000000000:  # before 2001
            raise ValueError("timestamp must be epoch milliseconds")
        return v


class SpeedSample(BaseModel):
    """GPS speed sample (time, speed, accuracy; no coordinates). Coordinates are never accepted."""

    model_config = ConfigDict(extra="forbid")

    t: int = Field(description="Fix time, epoch milliseconds (UTC).", examples=[_EPOCH_MS])
    speed: float | None = Field(None, ge=0, description="Ground speed, m/s.", examples=[13.4])
    accuracy: float | None = Field(
        None, ge=0, description="Horizontal accuracy radius, metres.", examples=[5.0]
    )


class TripChunkRequest(BaseModel):
    """Request body of POST /v1/trips/{trip_id}/chunks (one slice of sensor data)."""

    model_config = ConfigDict(extra="forbid")

    seq: int = Field(
        ...,
        ge=0,
        description="Chunk sequence number from 0; re-sending a seq is idempotent.",
        examples=[0],
    )
    imu: list[IMUSample] = Field(
        ..., min_length=1, description="IMU samples in ascending time order."
    )
    speed_samples: list[SpeedSample] = Field(
        ..., min_length=1, description="GPS speed samples in ascending time order."
    )
    car_connected: bool | None = Field(
        None,
        description="Whether the phone was connected to the car via Bluetooth during this chunk.",
        examples=[True],
    )

    @field_validator("imu")
    @classmethod
    def imu_timestamps_in_order(cls, v: Any) -> Any:
        for i in range(1, len(v)):
            if v[i].t < v[i - 1].t:
                raise ValueError("IMU timestamps must be in ascending order")
        return v

    @field_validator("speed_samples")
    @classmethod
    def speed_sample_timestamps_in_order(cls, v: Any) -> Any:
        for i in range(1, len(v)):
            if v[i].t < v[i - 1].t:
                raise ValueError("Speed sample timestamps must be in ascending order")
        return v


class TripChunkResponse(BaseModel):
    """Response of POST /v1/trips/{trip_id}/chunks."""

    status: Literal["received", "already_received"] = Field(
        description="already_received when this seq was uploaded before."
    )
    received_at: datetime = Field(
        description="When the chunk was first stored (UTC).", examples=[_TS]
    )


class TripEndResponse(BaseModel):
    """Response of POST /v1/trips/{trip_id}/end."""

    status: Literal["processing"] = Field(description="Trip is queued for processing.")


class TripStatusResponse(BaseModel):
    """Response of GET /v1/trips/{trip_id}/status."""

    trip_id: str = Field(description="Trip id.", examples=[_TRIP_ID])
    status: TripStatus = Field(description="Processing state of the trip.")
    failure_reason: str | None = Field(
        None, description="Why processing failed; only set when status is failed."
    )


# --- Processing Results ---


class EventResponse(BaseModel):
    """A detected driving event within a trip."""

    type: EventType = Field(description="Kind of event.")
    time: datetime = Field(description="When it happened (UTC).", examples=[_TS])
    peak_g: float | None = Field(
        description="Peak acceleration in g; null for speeding events.", examples=[0.45]
    )


class TripDetailResponse(BaseModel):
    """Response of GET /v1/me/trips/{trip_id}."""

    trip_id: str = Field(description="Trip id.", examples=[_TRIP_ID])
    started_at: datetime = Field(description="Trip start (UTC).", examples=[_TS])
    ended_at: datetime | None = Field(description="Trip end (UTC); null while ongoing.")
    distance_km: float = Field(
        description="Distance driven, km (0 if not yet computed).", examples=[12.34]
    )
    duration_min: float | None = Field(
        description="Duration, minutes; null if not yet computed.", examples=[21.5]
    )
    score: int | None = Field(description="Trip score 0 to 100, higher is safer.", examples=[82])
    confidence: float | None = Field(
        description="Model output 0 to 1 (higher = riskier); score = 100 * (1 - confidence).",
        examples=[0.18],
    )
    tier: Tier | None = Field(description="Risk tier derived from score; null if unscored.")
    events: list[EventResponse] = Field(description="Detected events, in time order.")
    explanation: str | None = Field(description="Plain-language summary of the score.")


class TripListItem(BaseModel):
    """A trip row in trip lists."""

    trip_id: str = Field(description="Trip id.", examples=[_TRIP_ID])
    started_at: datetime = Field(description="Trip start (UTC).", examples=[_TS])
    distance_km: float = Field(description="Distance driven, km.", examples=[12.34])
    duration_min: float | None = Field(
        description="Duration, minutes; null if not yet computed.", examples=[21.5]
    )
    score: int | None = Field(description="Trip score 0 to 100; null if unscored.", examples=[82])
    tier: Tier | None = Field(description="Risk tier; null if unscored.")
    trip_type: TripType | None = Field(None, description="Who was driving; null until classified.")
    needs_confirmation: bool = Field(
        False, description="True when the app should ask the user to label this unknown trip."
    )
    label_source: LabelSource | None = Field(
        None, description="Who decided trip_type; null if unlabelled."
    )
    transit_line: str | None = Field(
        None,
        description="Detected transit line for transit trips.",
        examples=["MTR Tsuen Wan Line"],
    )


# --- Driver Reports ---


class DriverSummaryResponse(BaseModel):
    """Response of GET /v1/me/summary (90-day rolling window)."""

    driver_id: str = Field(description="Driver id.", examples=[_DRIVER_ID])
    score: int = Field(description="Average driver score 0 to 100, higher is safer.", examples=[78])
    confidence: float = Field(
        description="Average model output 0 to 1 (higher = riskier).", examples=[0.22]
    )
    tier: Tier = Field(description="Risk tier derived from score.")
    premium_multiplier: float = Field(
        description="Premium multiplier for the tier.", examples=[1.0]
    )
    trend: Trend = Field(description="Recent score movement.")
    total_trips_90d: int = Field(description="Scored trips in the last 90 days.", examples=[24])
    total_distance_km_90d: float = Field(
        description="Distance in the last 90 days, km.", examples=[310.5]
    )


# --- Insurer Reports ---


class InsurerOverviewResponse(BaseModel):
    """Response of GET /v1/insurer/overview."""

    total_drivers: int = Field(description="Drivers with at least one scored trip.", examples=[42])
    total_trips_90d: int = Field(description="Scored trips in the last 90 days.", examples=[310])
    tier_distribution: dict[Tier, int] = Field(
        description="Raw count of scored trips per tier (not percentages).",
        examples=[{"A": 10, "B": 20, "C": 5}],
    )
    average_multiplier: float = Field(
        description="Mean premium multiplier, weighted by trips per tier.", examples=[1.05]
    )


class InsurerDriverItem(BaseModel):
    """A driver row in the insurer driver list."""

    driver_id: str = Field(description="Driver id.", examples=[_DRIVER_ID])
    score: int = Field(description="Average driver score 0 to 100.", examples=[78])
    confidence: float = Field(
        description="Average model output 0 to 1 (higher = riskier).", examples=[0.22]
    )
    tier: Tier = Field(description="Risk tier derived from score.")
    premium_multiplier: float = Field(
        description="Premium multiplier for the tier.", examples=[1.0]
    )
    total_trips_90d: int = Field(description="Scored trips in the last 90 days.", examples=[24])
    total_distance_km_90d: float = Field(
        description="Distance in the last 90 days, km.", examples=[310.5]
    )


class InsurerDriverDetailResponse(BaseModel):
    """Response of GET /v1/insurer/drivers/{driver_id}."""

    model_config = ConfigDict(protected_namespaces=())

    driver_id: str = Field(description="Driver id.", examples=[_DRIVER_ID])
    score: int = Field(description="Average driver score 0 to 100.", examples=[78])
    confidence: float = Field(
        description="Average model output 0 to 1 (higher = riskier).", examples=[0.22]
    )
    tier: Tier = Field(description="Risk tier derived from score.")
    premium_multiplier: float = Field(
        description="Premium multiplier for the tier.", examples=[1.0]
    )
    event_rates: dict[EventType, int] = Field(
        description="Raw event counts by type over the last 90 days (counts, not rates per km).",
        examples=[{"harsh_brake": 4, "speeding": 7}],
    )
    trips: list[TripListItem] = Field(description="Most recent 20 trips, newest first.")
    model_version: str = Field(
        description="Model version of the latest scored trip; 'unknown' if none.", examples=["v1"]
    )
    passenger_share: float = Field(
        0.0, description="Share of trips classified passenger or transit (0 to 1).", examples=[0.1]
    )
    label_sources: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Trip counts by label source. Keys: user, bluetooth, rules, unlabelled "
            "(empty object when the driver has no trips)."
        ),
        examples=[{"user": 2, "bluetooth": 10, "rules": 3, "unlabelled": 1}],
    )
    flagged_for_review: bool = Field(
        False, description="True when passenger_share exceeds the review threshold."
    )


class TripLabelRequest(BaseModel):
    """Request body of POST /v1/me/trips/{trip_id}/label."""

    trip_type: Literal["driver", "passenger"] = Field(
        ..., description="Label chosen by the driver.", examples=["driver"]
    )


class TripLabelResponse(BaseModel):
    """Response of POST /v1/me/trips/{trip_id}/label."""

    trip_id: str = Field(description="Trip id.", examples=[_TRIP_ID])
    trip_type: Literal["driver", "passenger"] = Field(description="Label that was stored.")
    status: Literal["added_to_score", "removed_from_score", "relabelled"] = Field(
        description="Effect on the driver's score."
    )


# --- Incidents ---


class SensorSnapshot(BaseModel):
    """Summary of sensor data around a crash. Unknown keys (e.g. coordinates) are rejected."""

    model_config = ConfigDict(extra="forbid")

    peak_g: float | None = Field(None, description="Peak acceleration, g.", examples=[5.2])
    imu_samples: int | None = Field(
        None, description="Number of IMU samples in the window.", examples=[750]
    )
    duration_ms: int | None = Field(
        None, description="Window length, milliseconds.", examples=[15000]
    )


class IncidentCreate(BaseModel):
    """Request body of POST /v1/me/incidents."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(
        "crash", description="Incident kind; only crash is produced today.", examples=["crash"]
    )
    time: datetime = Field(
        description="When it happened; naive values are read as UTC.", examples=[_TS]
    )
    peak_g: float | None = Field(None, description="Peak acceleration, g.", examples=[5.2])
    trip_id: str | None = Field(None, description="Related trip id, if any.", examples=[_TRIP_ID])
    sensor_snapshot: SensorSnapshot | None = Field(
        None, description="Sensor summary around the incident."
    )

    @field_validator("time")
    @classmethod
    def _time_utc(cls, v: datetime) -> datetime:
        return v.replace(tzinfo=UTC) if v.tzinfo is None else v


class IncidentConfirm(BaseModel):
    """Request body of POST /v1/me/incidents/{incident_id}/confirm."""

    confirmed: IncidentConfirmation = Field(
        ..., description="The driver's answer after a crash alert."
    )


class IncidentResponse(BaseModel):
    """An incident record."""

    id: int = Field(description="Incident id.", examples=[1])
    type: str = Field(description="Incident kind, e.g. crash.", examples=["crash"])
    time: datetime = Field(description="When it happened (UTC).", examples=[_TS])
    peak_g: float | None = Field(description="Peak acceleration, g.", examples=[5.2])
    confirmed: IncidentConfirmation | None = Field(
        description="Driver's answer; null until confirmed."
    )
    created_at: datetime = Field(description="Record creation (UTC).", examples=[_TS])


# --- Admin ---


class ReprocessResponse(BaseModel):
    """Response of POST /v1/trips/{trip_id}/reprocess."""

    trip_id: str = Field(description="Trip id.", examples=[_TRIP_ID])
    status: Literal["processing"] = Field(description="Trip was queued again.")


class DeleteDriverResponse(BaseModel):
    """Response of DELETE /v1/me."""

    status: Literal["deleted"] = Field(description="Always deleted.")
    deleted_files: int = Field(description="Raw chunk files removed from disk.", examples=[5])
