from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.values import (
    EventType,
    IncidentConfirmation,
    LabelSource,
    Tier,
    TripStatus,
    TripType,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Driver(Base):
    """A registered driver (one API key)."""

    __tablename__ = "drivers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    api_key_hash: Mapped[str] = mapped_column(String, nullable=False)
    emergency_contact_name: Mapped[str | None] = mapped_column(String, nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    trips: Mapped[list["Trip"]] = relationship("Trip", back_populates="driver")


class Consent(Base):
    """A consent version a driver accepted."""

    __tablename__ = "consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    driver_id: Mapped[str] = mapped_column(
        String, ForeignKey("drivers.id"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Trip(Base):
    """One recorded drive and its processing state."""

    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    driver_id: Mapped[str] = mapped_column(
        String, ForeignKey("drivers.id"), nullable=False, index=True
    )
    status: Mapped[TripStatus] = mapped_column(
        String,
        nullable=False,
        comment="uploading, processing, done, failed (see docs/data-model.md)",
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    trip_type: Mapped[TripType | None] = mapped_column(
        String,
        nullable=True,
        comment="driver, passenger, transit, unknown; null until classified",
    )
    label_source: Mapped[LabelSource | None] = mapped_column(
        String,
        nullable=True,
        comment="Who decided trip_type: bluetooth, rules, user; null if unlabelled",
    )
    driver_likelihood: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Classifier probability 0 to 1 that the user was driving"
    )
    transit_line: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Matched transit line name for transit trips"
    )
    bluetooth_connected_ratio: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Share 0 to 1 of the trip the phone was on car Bluetooth"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    driver: Mapped["Driver"] = relationship("Driver", back_populates="trips")
    chunks: Mapped[list["TripChunk"]] = relationship("TripChunk", back_populates="trip")
    events: Mapped[list["Event"]] = relationship("Event", back_populates="trip")
    features: Mapped["TripFeature | None"] = relationship(
        "TripFeature", back_populates="trip", uselist=False
    )
    score: Mapped["TripScore | None"] = relationship(
        "TripScore", back_populates="trip", uselist=False
    )


class TripChunk(Base):
    """One uploaded slice of raw sensor data for a trip (file on disk)."""

    __tablename__ = "trip_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[str] = mapped_column(String, ForeignKey("trips.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(
        String, nullable=False, comment="Gzipped JSON chunk file under DATA_DIR"
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    trip: Mapped["Trip"] = relationship("Trip", back_populates="chunks")

    __table_args__ = (UniqueConstraint("trip_id", "seq", name="uq_trip_chunk"),)


class Event(Base):
    """A driving event detected in a trip."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[str] = mapped_column(String, ForeignKey("trips.id"), nullable=False, index=True)
    type: Mapped[EventType] = mapped_column(
        String, nullable=False, comment="harsh_brake, harsh_accel, sharp_corner, speeding"
    )
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    peak_g: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Peak acceleration in g; null for speeding"
    )
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    trip: Mapped["Trip"] = relationship("Trip", back_populates="events")


class TripFeature(Base):
    """Computed features of a trip (contract: app/features.py)."""

    __tablename__ = "trip_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[str] = mapped_column(
        String, ForeignKey("trips.id"), nullable=False, unique=True
    )
    features: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="TripFeatures JSON (app/features.py)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    trip: Mapped["Trip"] = relationship("Trip", back_populates="features")


class TripScore(Base):
    """The model score and tier of a trip."""

    __tablename__ = "trip_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[str] = mapped_column(
        String, ForeignKey("trips.id"), nullable=False, unique=True
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Model output 0 to 1, higher = riskier; score = 100 * (1 - confidence)",
    )
    score: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Trip score 0 to 100, higher is safer"
    )
    tier: Mapped[Tier] = mapped_column(
        String,
        nullable=False,
        comment="Risk tier A to E from score (A >= 90, B >= 75, C >= 60, D >= 40)",
    )
    model_version: Mapped[str] = mapped_column(
        String, nullable=False, comment="Version of the model that produced the score"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    trip: Mapped["Trip"] = relationship("Trip", back_populates="score")


class Incident(Base):
    """A detected or reported crash."""

    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    driver_id: Mapped[str] = mapped_column(
        String, ForeignKey("drivers.id"), nullable=False, index=True
    )
    trip_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("trips.id"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String, nullable=False, comment="Incident kind; crash")
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_g: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Peak acceleration in g"
    )
    confirmed: Mapped[IncidentConfirmation | None] = mapped_column(
        String, nullable=True, comment="Driver answer: ok, help_needed, no_response; null if none"
    )
    sensor_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="JSON with peak_g, imu_samples, duration_ms around the crash"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
