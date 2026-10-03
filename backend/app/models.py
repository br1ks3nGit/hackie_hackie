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


def utcnow() -> datetime:
    return datetime.now(UTC)


class Driver(Base):
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
    __tablename__ = "consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    driver_id: Mapped[str] = mapped_column(String, ForeignKey("drivers.id"), nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    driver_id: Mapped[str] = mapped_column(String, ForeignKey("drivers.id"), nullable=False)
    # uploading, processing, done, failed
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # driver, passenger, transit, unknown
    trip_type: Mapped[str | None] = mapped_column(String, nullable=True)
    # bluetooth, rules, user
    label_source: Mapped[str | None] = mapped_column(String, nullable=True)
    driver_likelihood: Mapped[float | None] = mapped_column(Float, nullable=True)
    transit_line: Mapped[str | None] = mapped_column(String, nullable=True)
    bluetooth_connected_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
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
    __tablename__ = "trip_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[str] = mapped_column(String, ForeignKey("trips.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    trip: Mapped["Trip"] = relationship("Trip", back_populates="chunks")

    __table_args__ = (UniqueConstraint("trip_id", "seq", name="uq_trip_chunk"),)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[str] = mapped_column(String, ForeignKey("trips.id"), nullable=False)
    # harsh_brake, harsh_accel, sharp_corner, speeding
    type: Mapped[str] = mapped_column(String, nullable=False)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    peak_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    trip: Mapped["Trip"] = relationship("Trip", back_populates="events")


class TripFeature(Base):
    __tablename__ = "trip_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[str] = mapped_column(
        String, ForeignKey("trips.id"), nullable=False, unique=True
    )
    features: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    trip: Mapped["Trip"] = relationship("Trip", back_populates="features")


class TripScore(Base):
    __tablename__ = "trip_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[str] = mapped_column(
        String, ForeignKey("trips.id"), nullable=False, unique=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    tier: Mapped[str] = mapped_column(String, nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    trip: Mapped["Trip"] = relationship("Trip", back_populates="score")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    driver_id: Mapped[str] = mapped_column(String, ForeignKey("drivers.id"), nullable=False)
    trip_id: Mapped[str | None] = mapped_column(String, ForeignKey("trips.id"), nullable=True)
    type: Mapped[str] = mapped_column(String, nullable=False)  # crash
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    # ok, help_needed, no_response
    confirmed: Mapped[str | None] = mapped_column(String, nullable=True)
    sensor_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
