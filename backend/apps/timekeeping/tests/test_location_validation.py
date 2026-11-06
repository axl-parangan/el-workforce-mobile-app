from decimal import Decimal

import pytest

from apps.jobs.constants import DEFAULT_GEOFENCE_RADIUS_METERS
from apps.timekeeping.services.location_validation import (
    CircularGeofence,
    Coordinates,
    LocationStatus,
    assess_punch_location,
    build_job_geofence,
    distance_meters,
)

SITE = Coordinates(Decimal("43.642600"), Decimal("-79.387100"))
GEOFENCE = CircularGeofence(center=SITE, radius_meters=Decimal("100"))

# 0.0005 degrees of latitude is ~55.6 m; 0.0010 is ~111.2 m.
INSIDE = ("43.643100", "-79.387100")
OUTSIDE = ("43.643600", "-79.387100")


def assess(latlng=INSIDE, accuracy="10", geofence=GEOFENCE, **kwargs):
    latitude, longitude = latlng if latlng is not None else (None, None)
    return assess_punch_location(
        latitude=latitude,
        longitude=longitude,
        accuracy_meters=accuracy,
        geofence=geofence,
        **kwargs,
    )


# --- distance --------------------------------------------------------------------


def test_distance_for_one_thousandth_degree_of_latitude():
    outside = Coordinates(Decimal(OUTSIDE[0]), Decimal(OUTSIDE[1]))

    assert distance_meters(SITE, outside) == Decimal("111.20")


def test_distance_accounts_for_longitude_convergence():
    east = Coordinates(SITE.latitude, SITE.longitude + Decimal("0.001"))

    assert Decimal("80") < distance_meters(SITE, east) < Decimal("81")


# --- verified -----------------------------------------------------------------------


def test_inside_geofence_with_good_accuracy_is_verified():
    result = assess()

    assert result.status == LocationStatus.VERIFIED
    assert result.flags == ()
    assert result.requires_review is False
    assert result.coordinates == Coordinates(Decimal("43.643100"), Decimal("-79.387100"))
    assert result.accuracy_meters == Decimal("10.00")
    assert result.distance_meters == Decimal("55.60")


def test_point_exactly_on_the_radius_is_inside():
    geofence = CircularGeofence(center=SITE, radius_meters=Decimal("111.20"))

    assert assess(OUTSIDE, geofence=geofence).status == LocationStatus.VERIFIED


# --- outside geofence / accuracy ------------------------------------------------------


def test_outside_geofence_is_flagged_and_keeps_coordinates():
    result = assess(OUTSIDE)

    assert result.status == LocationStatus.OUTSIDE_GEOFENCE
    assert result.requires_review is True
    assert result.coordinates is not None
    assert result.distance_meters == Decimal("111.20")


@pytest.mark.parametrize(
    ("accuracy", "expected_flags"),
    [
        ("30", ()),
        ("30.01", (LocationStatus.LOW_ACCURACY,)),
        ("250", (LocationStatus.LOW_ACCURACY,)),
        (None, (LocationStatus.ACCURACY_UNKNOWN,)),
        ("-1", (LocationStatus.ACCURACY_UNKNOWN,)),
        ("fast", (LocationStatus.ACCURACY_UNKNOWN,)),
    ],
)
def test_accuracy_threshold_is_30_metres_inclusive(accuracy, expected_flags):
    result = assess(accuracy=accuracy)

    assert result.flags == expected_flags
    assert result.coordinates is not None  # poor accuracy never discards coordinates


def test_low_accuracy_keeps_coordinates_and_accuracy():
    result = assess(accuracy="80")

    assert result.status == LocationStatus.LOW_ACCURACY
    assert result.accuracy_meters == Decimal("80.00")
    assert result.distance_meters == Decimal("55.60")


def test_outside_and_inaccurate_reports_both_flags_with_outside_as_primary():
    result = assess(OUTSIDE, accuracy="80")

    assert result.status == LocationStatus.OUTSIDE_GEOFENCE
    assert result.flags == (LocationStatus.OUTSIDE_GEOFENCE, LocationStatus.LOW_ACCURACY)


def test_accuracy_threshold_comes_from_settings(settings):
    settings.LOCATION_MAX_ACCURACY_METERS = Decimal("5")

    assert assess(accuracy="10").status == LocationStatus.LOW_ACCURACY


# --- missing / invalid coordinates ------------------------------------------------------


def test_missing_location_is_flagged_unavailable():
    result = assess(latlng=None, accuracy=None)

    assert result.status == LocationStatus.LOCATION_UNAVAILABLE
    assert result.requires_review is True
    assert result.coordinates is None
    assert result.distance_meters is None


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        ("90.0001", "0"),
        ("-91", "0"),
        ("0", "180.5"),
        ("0", "-181"),
        ("abc", "0"),
        ("NaN", "0"),
        ("0", "Infinity"),
        (None, "0"),  # partial payload
        ("0", None),
        (True, "0"),
        ({"lat": 1}, "0"),
    ],
)
def test_invalid_coordinates_are_discarded_and_flagged_never_raised(latitude, longitude):
    result = assess_punch_location(
        latitude=latitude, longitude=longitude, accuracy_meters="5", geofence=GEOFENCE
    )

    assert result.status == LocationStatus.INVALID_COORDINATES
    assert result.requires_review is True
    assert result.coordinates is None
    assert result.accuracy_meters is None
    assert result.distance_meters is None


def test_coordinates_are_quantized_to_storage_precision():
    result = assess(latlng=("43.64310049", "-79.38710051"))

    assert result.coordinates == Coordinates(Decimal("43.643100"), Decimal("-79.387101"))


def test_numbers_are_accepted_as_well_as_strings():
    result = assess(latlng=(43.6431, -79.3871), accuracy=12.5)

    assert result.status == LocationStatus.VERIFIED
    assert result.accuracy_meters == Decimal("12.50")


# --- jobs without a geofence -------------------------------------------------------


def test_job_without_geofence_is_not_flagged_outside_and_not_sent_to_review():
    result = assess(OUTSIDE, geofence=None)

    assert result.status == LocationStatus.GEOFENCE_NOT_CONFIGURED
    assert LocationStatus.OUTSIDE_GEOFENCE not in result.flags
    assert result.requires_review is False
    assert result.coordinates is not None
    assert result.distance_meters is None


def test_job_without_geofence_still_reports_gps_problems():
    result = assess(geofence=None, accuracy="80")

    assert result.flags == (LocationStatus.LOW_ACCURACY, LocationStatus.GEOFENCE_NOT_CONFIGURED)
    assert result.status == LocationStatus.LOW_ACCURACY
    assert result.requires_review is True


def test_job_without_geofence_and_no_location():
    result = assess(latlng=None, geofence=None)

    assert result.flags == (
        LocationStatus.LOCATION_UNAVAILABLE,
        LocationStatus.GEOFENCE_NOT_CONFIGURED,
    )


# --- job geofence construction ------------------------------------------------------


def test_job_without_coordinates_has_no_geofence():
    assert build_job_geofence(latitude=None, longitude=None, radius_meters=None) is None
    assert build_job_geofence(latitude=None, longitude=None, radius_meters=Decimal("50")) is None


def test_job_with_coordinates_but_no_radius_uses_100_metre_default():
    geofence = build_job_geofence(
        latitude=SITE.latitude, longitude=SITE.longitude, radius_meters=None
    )

    assert geofence == CircularGeofence(SITE, Decimal("100"))
    assert Decimal("100") == DEFAULT_GEOFENCE_RADIUS_METERS


def test_job_radius_is_customisable():
    # Job.geofence_radius_meters is an integer column.
    geofence = build_job_geofence(
        latitude=SITE.latitude, longitude=SITE.longitude, radius_meters=250
    )

    assert geofence is not None
    assert geofence.radius_meters == Decimal("250")


def test_non_positive_radius_is_a_programming_error():
    with pytest.raises(ValueError, match="positive"):
        build_job_geofence(
            latitude=SITE.latitude, longitude=SITE.longitude, radius_meters=Decimal("0")
        )
