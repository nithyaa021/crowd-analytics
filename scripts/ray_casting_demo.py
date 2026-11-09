"""A tiny point-in-polygon demo in pure Python, to explain what cv2.pointPolygonTest does.

Why this file exists: the app uses cv2.pointPolygonTest, which is fast but is a black box. If a
panel asks "how does the app know a person is inside a zone?", this file answers it with 30
lines of readable maths and no OpenCV at all.

This file is for learning only. The app never imports it, and it is deliberately not used by
app/zones.py, so a mistake here can never affect the real counting.

Run: .venv\\Scripts\\python.exe scripts\\ray_casting_demo.py
"""

# The square zone used in every example below: x from 100 to 200, y from 100 to 200.
SQUARE = [(100, 100), (200, 100), (200, 200), (100, 200)]

# The points we test, with the answer we expect, so the demo proves itself.
CASES = [
    ((150, 150), True, "middle of the square"),
    ((50, 50), False, "diagonally outside"),
    ((100, 150), True, "exactly on the left edge"),
    ((250, 150), False, "to the right of the square"),
    ((150, 90), False, "just above the top edge"),
]


def on_segment(point: tuple[float, float], a: tuple[float, float],
               b: tuple[float, float]) -> bool:
    """True when the point lies exactly on the straight line between a and b.

    Why this is a separate check: ray casting alone cannot answer "on the border", because a
    point sitting exactly on an edge is neither clearly inside nor outside. OpenCV reports 0
    for that case, and we treat 0 as inside, so this function reproduces that behaviour.

    Numeric example: point (100, 150) on the edge from (100, 100) to (100, 200) -> True.
    """
    # Cross product zero means all three points are in a straight line.
    cross = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])
    if abs(cross) > 1e-9:
        return False
    # A zero cross product alone is not enough: the point must also sit between the two ends.
    return (min(a[0], b[0]) <= point[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= point[1] <= max(a[1], b[1]))


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    """Answers "is this point inside this polygon?" by casting a ray to the right.

    The idea (ray casting):
    Imagine standing at the point and shooting a laser straight to the right. Every time the
    laser crosses an edge of the polygon, we flip a switch: outside -> inside -> outside.
    If we end with the switch ON, an odd number of edges were crossed, so the point is inside.
    An even number means the laser went in and came back out, so the point is outside.

    Two details make it match OpenCV:
      1. A point exactly ON an edge counts as inside, so we check that first and stop.
      2. The ray only counts crossings strictly to the right (crossing_x > x), never exactly
         on the point. Otherwise an edge passing through the point would be counted twice and
         a point on the border would look outside.

    Numeric example: point (150, 150) against the square above.
      Edge (200,100)-(200,200): the ray crosses it at x = 200, which is > 150, so flip -> inside.
      Edge (100,100)-(100,200): x = 100 is behind us, so ignore.
      One flip = odd = inside. Correct.
    """
    count = len(polygon)
    # Border first: this is the case plain ray casting gets wrong.
    for index in range(count):
        if on_segment(point, polygon[index], polygon[(index + 1) % count]):
            return True

    inside = False
    for index in range(count):
        x1, y1 = polygon[index]
        # The last point joins back to the first, which closes the polygon.
        x2, y2 = polygon[(index + 1) % count]

        # A horizontal edge can never be crossed by a horizontal ray, so skip it.
        if y1 == y2:
            continue

        # Is the ray's height between this edge's two ends? If not, the ray misses the edge.
        if not (min(y1, y2) <= point[1] <= max(y1, y2)):
            continue

        # x position where the edge crosses the point's height, using linear interpolation.
        crossing_x = x1 + (point[1] - y1) * (x2 - x1) / (y2 - y1)

        # Only edges strictly to the right can be hit by a ray going right.
        if crossing_x > point[0]:
            inside = not inside
    return inside


def main() -> None:
    """Runs every example case and prints whether the function agreed with the expectation."""
    print(f"Polygon: {SQUARE}\n")
    passed = 0
    for point, expected, description in CASES:
        actual = point_in_polygon(point, SQUARE)
        verdict = "PASS" if actual == expected else "FAIL"
        print(f"  {verdict}  {str(point):12s} inside={str(actual):5s} "
              f"(expected {str(expected):5s})  {description}")
        passed += 1 if actual == expected else 0
    print(f"\n{passed}/{len(CASES)} cases agreed with the expectation.")


if __name__ == "__main__":
    main()
