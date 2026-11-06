"""Punch location assessment (ADR 004).

Attendance recording and location validation are separate concerns: nothing
in this module can prevent a punch from being recorded. Bad or missing GPS
data is discarded and flagged instead.

Pure functions with no database access, so the rules can be tested
exhaustively and reused by every endpoint that accepts punches. The API
serializer must therefore accept the raw latitude/longitude/accuracy values
without validating them and hand them to ``assess_punch_location``.

Only circular geofences exist today. A polygon geofence would be added as a
new geofence type in this module; callers keep the same inputs and result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.conf import settings

from apps.jobs.constants import DEFAULT_GEOFENCE_RADIUS_METERS
from apps.timekeeping.models.choices import LocationStatus

# Storage precision, matching AttendanceBatch:
#   latitude/longitude: DecimalField(max_digits=9, decimal_places=6)  (~0.1 m)
#   accuracy/distance:  DecimalField(max_digits=10, decimal_places=2)
COORDINATE_QUANTUM = Decimal("0.000001")
METERS_QUANTUM = Decimal("0.01")
MAX_STORABLE_METERS = Decimal("99999999.99")

# Mean Earth radius (IUGG). Haversine error is well under 0.5% at these scales.
EARTH_RADIUS_METERS = 6_371_008.8


# Order decides which flag becomes the primary status when several apply.
# Conditions that need review come first; informational ones last.
_PRECEDENCE: tuple[LocationStatus, ...] = (
    LocationStatus.INVALID_COORDINATES,
    LocationStatus.LOCATION_UNAVAILABLE,
    LocationStatus.OUTSIDE_GEOFENCE,
    LocationStatus.LOW_ACCURACY,
    LocationStatus.ACCURACY_UNKNOWN,
    LocationStatus.GEOFENCE_NOT_CONFIGURED,
)

# A job without a geofence is a configuration gap, not a worker issue, so on
# its own it does not put the punch in the review queue (documented assumption).
_INFORMATIONAL: frozenset[LocationStatus] = frozenset({LocationStatus.GEOFENCE_NOT_CONFIGURED})


@dataclass(frozen=True)
class Coordinates:
    latitude: Decimal
    longitude: Decimal


@dataclass(frozen=True)
class CircularGeofence:
    center: Coordinates
    radius_meters: Decimal


@dataclass(frozen=True)
class LocationAssessment:
    """What to store on the punch event."""

    status: LocationStatus
    flags: tuple[LocationStatus, ...]
    requires_review: bool
    # Sanitised values: None when missing or discarded as invalid.
    coordinates: Coordinates | None
    accuracy_meters: Decimal | None
    # Distance from the geofence centre; None without coordinates or geofence.
    distance_meters: Decimal | None

    @property
    def review_flags(self) -> tuple[LocationStatus, ...]:
        """The flags that put a punch's session into review."""
        return tuple(flag for flag in self.flags if flag not in _INFORMATIONAL)


def flags_require_review(flags: list[str] | tuple[str, ...]) -> bool:
    """Same rule as LocationAssessment.requires_review, for flags read back from storage."""
    return any(flag not in _INFORMATIONAL for flag in flags)


def _to_decimal(value: object) -> Decimal | None:
    """Best-effort numeric parse. Returns None instead of raising."""
    if isinstance(value, bool) or not isinstance(value, Decimal | int | float | str):
        return None
    try:
        # str() keeps the value as the client sent it instead of float's binary expansion.
        number = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _parse_coordinates(latitude: object, longitude: object) -> Coordinates | None:
    lat, lng = _to_decimal(latitude), _to_decimal(longitude)
    if lat is None or lng is None:
        return None
    if not (Decimal(-90) <= lat <= Decimal(90) and Decimal(-180) <= lng <= Decimal(180)):
        return None
    return Coordinates(lat.quantize(COORDINATE_QUANTUM), lng.quantize(COORDINATE_QUANTUM))


def _parse_accuracy(accuracy_meters: object) -> Decimal | None:
    accuracy = _to_decimal(accuracy_meters)
    if accuracy is None or accuracy < 0 or accuracy > MAX_STORABLE_METERS:
        return None
    return accuracy.quantize(METERS_QUANTUM)


def build_job_geofence(
    *,
    latitude: Decimal | None,
    longitude: Decimal | None,
    radius_meters: int | Decimal | None,
) -> CircularGeofence | None:
    """The job's geofence, or None when the job has no coordinates.

    A missing radius falls back to DEFAULT_GEOFENCE_RADIUS_METERS (100 m).
    """
    if latitude is None or longitude is None:
        return None
    radius = Decimal(radius_meters if radius_meters is not None else DEFAULT_GEOFENCE_RADIUS_METERS)
    if radius <= 0:
        raise ValueError("Geofence radius must be positive.")
    return CircularGeofence(Coordinates(latitude, longitude), radius)


def distance_meters(a: Coordinates, b: Coordinates) -> Decimal:
    """Great-circle (haversine) distance, rounded to centimetres.

    Trigonometry needs floats; the result is converted back to Decimal for
    storage and threshold comparison. This is a measurement, not money.
    """
    lat1, lat2 = math.radians(float(a.latitude)), math.radians(float(b.latitude))
    d_lat = lat2 - lat1
    d_lng = math.radians(float(b.longitude) - float(a.longitude))
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lng / 2) ** 2
    meters = 2 * EARTH_RADIUS_METERS * math.asin(min(1.0, math.sqrt(h)))
    return Decimal(str(meters)).quantize(METERS_QUANTUM)


def assess_punch_location(
    *,
    latitude: object,
    longitude: object,
    accuracy_meters: object,
    geofence: CircularGeofence | None,
    max_accuracy_meters: Decimal | None = None,
) -> LocationAssessment:
    """Classify a punch's raw location payload. Never raises for bad GPS data.

    - No coordinates sent             -> location_unavailable (flagged)
    - Malformed / out-of-range values -> coordinates discarded, invalid_coordinates (flagged)
    - Accuracy worse than threshold   -> coordinates kept, low_accuracy (flagged)
    - Accuracy missing or invalid     -> coordinates kept, accuracy_unknown (flagged)
    - Outside the job geofence        -> outside_geofence (flagged)
    - Job has no geofence             -> geofence_not_configured (not flagged on its own)
    """
    max_accuracy = (
        max_accuracy_meters
        if max_accuracy_meters is not None
        else settings.LOCATION_MAX_ACCURACY_METERS
    )
    flags: set[LocationStatus] = set()

    coordinates: Coordinates | None = None
    if latitude is None and longitude is None:
        flags.add(LocationStatus.LOCATION_UNAVAILABLE)
    else:
        coordinates = _parse_coordinates(latitude, longitude)
        if coordinates is None:
            flags.add(LocationStatus.INVALID_COORDINATES)

    accuracy: Decimal | None = None
    if coordinates is not None:
        accuracy = _parse_accuracy(accuracy_meters)
        if accuracy is None:
            flags.add(LocationStatus.ACCURACY_UNKNOWN)
        elif accuracy > max_accuracy:
            flags.add(LocationStatus.LOW_ACCURACY)

    distance: Decimal | None = None
    if geofence is None:
        flags.add(LocationStatus.GEOFENCE_NOT_CONFIGURED)
    elif coordinates is not None:
        distance = distance_meters(coordinates, geofence.center)
        if distance > geofence.radius_meters:
            flags.add(LocationStatus.OUTSIDE_GEOFENCE)

    ordered = tuple(status for status in _PRECEDENCE if status in flags)
    return LocationAssessment(
        status=ordered[0] if ordered else LocationStatus.VERIFIED,
        flags=ordered,
        requires_review=any(flag not in _INFORMATIONAL for flag in ordered),
        coordinates=coordinates,
        accuracy_meters=accuracy,
        distance_meters=distance,
    )
