# save this function for wall construction
def calculate_geometry(self, sub_surface):
    """
    Calculate the length, width, perimeter, and area of the window from its vertices.
    Assumes the window is a quadrilateral (typically a rectangle).
    """
    vertices = sub_surface.vertices()
    if len(vertices) != 4:
        return {
            "length": 0.0,
            "width": 0.0,
            "perimeter": 0.0,
            "area": 0.0
        }

    # Calculate all edge lengths
    edge_lengths = []
    perimeter = 0.0
    for i in range(4):
        v1 = vertices[i]
        v2 = vertices[(i + 1) % 4]
        edge = v2 - v1
        length = edge.length()
        edge_lengths.append(length)
        perimeter += length

    # Assume opposite edges are equal, so we can group into two unique lengths
    length = max(edge_lengths)
    width = min(edge_lengths)

    # Area = length × width
    area = length * width

    return {
        "length": length,
        "width": width,
        "perimeter": perimeter,
        "area": area
    }