from django.contrib.gis.geos import Point

APPROX_LOCATION_STEP = 0.005  # градусы, примерно 500 м


def round_point(point):
    """Округляет точку, чтобы не хранить точное местоположение пользователя."""
    if point is None:
        return None
    return Point(
        round(round(point.x / APPROX_LOCATION_STEP) * APPROX_LOCATION_STEP, 6),
        round(round(point.y / APPROX_LOCATION_STEP) * APPROX_LOCATION_STEP, 6),
        srid=4326,
    )
