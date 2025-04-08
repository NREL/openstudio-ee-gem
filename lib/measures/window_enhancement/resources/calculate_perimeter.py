# save this function for wall construction
def calculate_perimeter(self, sub_surface):
    """Calculate the perimeter of the window from its vertices."""
    vertices = sub_surface.vertices()
    if len(vertices) < 2:
        return 0.0

    perimeter = 0.0
    num_vertices = len(vertices)

    for i in range(num_vertices):
        v1 = vertices[i]
        v2 = vertices[(i + 1) % num_vertices]  # Wrap around to the first vertex
        edge_vector = v2 - v1  # Subtract two Point3d objects to get Vector3d
        edge_length = edge_vector.length()  # Use length() to get the magnitude of the vector
        perimeter += edge_length

    return perimeter