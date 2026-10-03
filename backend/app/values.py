"""Allowed values of enum-like fields, shared by models.py and schemas.py."""

from typing import Literal

# trips.status; set in routers/ingestion.py and pipeline.py
TripStatus = Literal["uploading", "processing", "done", "failed"]
# Risk tier from score_to_tier in app/model.py (A = best)
Tier = Literal["A", "B", "C", "D", "E"]
# trips.trip_type; set by classify.py (transit/driver/unknown) and user labels (driver/passenger)
TripType = Literal["driver", "passenger", "transit", "unknown"]
# trips.label_source; who decided trip_type (null when unlabelled)
LabelSource = Literal["bluetooth", "rules", "user"]
# events.type; produced by pipeline._detect_events
EventType = Literal["harsh_brake", "harsh_accel", "sharp_corner", "speeding"]
# Driver score trend from reports._calculate_driver_score
Trend = Literal["improving", "stable", "worsening"]
# incidents.confirmed; set by POST /v1/me/incidents/{id}/confirm
IncidentConfirmation = Literal["ok", "help_needed", "no_response"]
