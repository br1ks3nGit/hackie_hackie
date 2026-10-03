from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Driver(Base):
    __tablename__ = "drivers"

    id = Column(String, primary_key=True)
    api_key_hash = Column(String, nullable=False)
    emergency_contact_name = Column(String, nullable=True)
    emergency_contact_phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    trips = relationship("Trip", back_populates="driver")


class Consent(Base):
    __tablename__ = "consents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    driver_id = Column(String, ForeignKey("drivers.id"), nullable=False)
    version = Column(String, nullable=False)
    granted_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Trip(Base):
    __tablename__ = "trips"

    id = Column(String, primary_key=True)
    driver_id = Column(String, ForeignKey("drivers.id"), nullable=False)
    status = Column(String, nullable=False)  # uploading, processing, done, failed
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    failure_reason = Column(Text, nullable=True)
    trip_type = Column(String, nullable=True)  # driver, passenger, transit, unknown
    label_source = Column(String, nullable=True)  # bluetooth, rules, user
    driver_likelihood = Column(Float, nullable=True)
    transit_line = Column(String, nullable=True)
    bluetooth_connected_ratio = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    driver = relationship("Driver", back_populates="trips")
    chunks = relationship("TripChunk", back_populates="trip")
    events = relationship("Event", back_populates="trip")
    features = relationship("TripFeature", back_populates="trip", uselist=False)
    score = relationship("TripScore", back_populates="trip", uselist=False)


class TripChunk(Base):
    __tablename__ = "trip_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(String, ForeignKey("trips.id"), nullable=False)
    seq = Column(Integer, nullable=False)
    file_path = Column(String, nullable=False)
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    trip = relationship("Trip", back_populates="chunks")

    __table_args__ = (UniqueConstraint("trip_id", "seq", name="uq_trip_chunk"),)


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(String, ForeignKey("trips.id"), nullable=False)
    type = Column(String, nullable=False)  # harsh_brake, harsh_accel, sharp_corner, speeding
    time = Column(DateTime, nullable=False)
    peak_g = Column(Float, nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)

    trip = relationship("Trip", back_populates="events")


class TripFeature(Base):
    __tablename__ = "trip_features"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(String, ForeignKey("trips.id"), nullable=False, unique=True)
    features = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    trip = relationship("Trip", back_populates="features")


class TripScore(Base):
    __tablename__ = "trip_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(String, ForeignKey("trips.id"), nullable=False, unique=True)
    confidence = Column(Float, nullable=False)
    score = Column(Integer, nullable=False)
    tier = Column(String, nullable=False)
    model_version = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    trip = relationship("Trip", back_populates="score")


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    driver_id = Column(String, ForeignKey("drivers.id"), nullable=False)
    trip_id = Column(String, ForeignKey("trips.id"), nullable=True)
    type = Column(String, nullable=False)  # crash
    time = Column(DateTime, nullable=False)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    peak_g = Column(Float, nullable=True)
    confirmed = Column(String, nullable=True)  # ok, help_needed, no_response
    sensor_snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
