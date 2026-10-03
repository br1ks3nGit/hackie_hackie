"""Per-trip feature contract between the pipeline and the scoring model."""

from pydantic import BaseModel, Field


class RouteSample(BaseModel):
    """One downsampled GPS point of the trip route (about 100 points per trip)."""

    t: int = Field(description="Sample time, epoch milliseconds (UTC).", examples=[1767225600000])
    lat: float = Field(description="Latitude, degrees.", examples=[22.3193])
    lon: float = Field(description="Longitude, degrees.", examples=[114.1694])
    speed: float | None = Field(
        description="GPS speed in m/s; null when the sample had no speed.", examples=[13.4]
    )


class EventsPer100km(BaseModel):
    """Event rate per event type, normalised per 100 km (distance floored at 0.1 km)."""

    harsh_brake: float = Field(description="Harsh braking events per 100 km.", examples=[2.5])
    harsh_accel: float = Field(description="Harsh acceleration events per 100 km.", examples=[1.0])
    sharp_corner: float = Field(description="Sharp cornering events per 100 km.", examples=[0.0])
    speeding: float = Field(description="Speeding events per 100 km.", examples=[3.2])


class TripFeatures(BaseModel):
    """Features computed by `pipeline._calculate_features` and stored in trip_features.features.

    This is the contract with the model team. The model consumes a flat vector built from
    these fields in the order given by `FEATURE_ORDER` in `app/model.py`
    (`events_per_100km` is flattened to `<event>_per_100km`). `route` is not a model input;
    it only feeds the trip detail map. Changing a field name or unit here breaks the model.
    """

    distance_km: float = Field(description="Distance driven, kilometres.", examples=[12.34])
    duration_min: float = Field(description="Trip duration, minutes.", examples=[21.5])
    night_driving_share: float = Field(
        ge=0,
        le=1,
        description="Share of IMU samples between 23:00 and 05:59 Asia/Hong_Kong (0 to 1).",
        examples=[0.0],
    )
    events_per_100km: EventsPer100km = Field(description="Event rates per 100 km.")
    mean_speed_ms: float = Field(description="Mean GPS speed, m/s.", examples=[11.2])
    max_speed_ms: float = Field(description="Maximum GPS speed, m/s.", examples=[24.9])
    speeding_time_share: float = Field(
        ge=0,
        le=1,
        description="Share of GPS samples above the speeding threshold (0 to 1).",
        examples=[0.05],
    )
    route: list[RouteSample] = Field(description="Downsampled route points, in time order.")
