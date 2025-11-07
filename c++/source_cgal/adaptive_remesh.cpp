#include <CGAL/Simple_cartesian.h>
#include <CGAL/Surface_mesh.h>
#include <CGAL/Polygon_mesh_processing/remesh.h>
#include <CGAL/Polygon_mesh_processing/measure.h>
#include <CGAL/Polygon_mesh_processing/Adaptive_sizing_field.h>
#include <CGAL/Polygon_mesh_processing/IO/polygon_mesh_io.h>
#include <CGAL/Polygon_mesh_processing/distance.h>


#include <CGAL/Polygon_mesh_processing/compute_normal.h>
#include <cmath>
#include <limits>

#include <iostream>
#include <fstream>
#include <string>

namespace PMP = CGAL::Polygon_mesh_processing;

typedef CGAL::Simple_cartesian<double> Kernel;
typedef Kernel::Point_3                Point;
typedef CGAL::Surface_mesh<Point>      Mesh;

#define TAG CGAL::Parallel_if_available_tag

/**
 * Computes the average edge length of a mesh, optionally scaled by a factor.
 * 
 * @param mesh The input surface mesh
 * @param scale_factor Multiplicative factor applied to the average length (default: 1.0)
 * @return The computed target edge length, or 0.0 if the mesh has no edges
 */
double compute_target_edge_length(const Mesh& mesh, double scale_factor = 1.0)
{
    double total_length = 0.0;
    size_t edge_count = 0;

    for (auto e : edges(mesh)) {
        total_length += PMP::edge_length(e, mesh);
        ++edge_count;
    }

    if (edge_count == 0) return 0.0;

    double avg_length = total_length / static_cast<double>(edge_count);
    return avg_length * scale_factor;
}


/**
 * @brief Computes the target edge length for a given relative density and curvature radius.
 * 
 * This function estimates the edge length required to 
 * sample a sphere of a given radius with a specified relative density. A density of 1 
 * corresponds to approximately 16 points on the surface of a unit sphere.
 * 
 * The formula derives the average area per point and converts it to edge length assuming 
 * equilateral triangle coverage.
 * 
 * @param density The relative density value (e.g. 2.0 corresponds to ~32 points).
 * @param radius The curvature radius (local or average) of the geometry.
 * @return double The estimated target edge length.
 */
double edge_length_from_density(double density, double radius) {
    double n_points = 16.0 * density;
    double area_per_point = 4.0 * M_PI * radius * radius / n_points;
    return std::sqrt(4.0 * area_per_point / std::sqrt(3.0));
}


/**
 * @brief Estimates mean curvature at a vertex using the angle defect method.
 * 
 * This function computes an approximation of the mean curvature at a vertex
 * using the discrete Gaussian curvature (angle defect) divided by the local area.
 * The mean curvature is then estimated as K_H ≈ K_G / 2 (rough approximation).
 * 
 * @param v The vertex descriptor
 * @param mesh The surface mesh
 * @return double The estimated mean curvature at the vertex
 */
double estimate_mean_curvature(typename Mesh::Vertex_index v, const Mesh& mesh)
{
    typedef typename Mesh::Halfedge_index Halfedge_index;
    
    // Compute angle defect (discrete Gaussian curvature)
    double angle_sum = 0.0;
    double local_area = 0.0;
    
    // Iterate over incident faces
    for (Halfedge_index h : CGAL::halfedges_around_target(v, mesh)) {
        if (!mesh.is_border(h)) {
            auto face = mesh.face(h);
            
            // Get the three vertices of the face
            Halfedge_index h0 = mesh.halfedge(face);
            Halfedge_index h1 = mesh.next(h0);
            Halfedge_index h2 = mesh.next(h1);
            
            Point p0 = mesh.point(mesh.target(h0));
            Point p1 = mesh.point(mesh.target(h1));
            Point p2 = mesh.point(mesh.target(h2));
            
            // Compute face area
            CGAL::Vector_3<Kernel> v1 = p1 - p0;
            CGAL::Vector_3<Kernel> v2 = p2 - p0;
            double face_area = 0.5 * std::sqrt(CGAL::cross_product(v1, v2).squared_length());
            local_area += face_area / 3.0; // Distribute area to vertices
            
            // Compute angle at vertex v
            if (mesh.target(h) == v) {
                Point pv = mesh.point(v);
                Point p_prev = mesh.point(mesh.source(h));
                Point p_next = mesh.point(mesh.target(mesh.next(h)));
                
                CGAL::Vector_3<Kernel> vec1 = p_prev - pv;
                CGAL::Vector_3<Kernel> vec2 = p_next - pv;
                
                double dot = vec1 * vec2;
                double len1 = std::sqrt(vec1.squared_length());
                double len2 = std::sqrt(vec2.squared_length());
                
                if (len1 > 1e-10 && len2 > 1e-10) {
                    double cos_angle = dot / (len1 * len2);
                    cos_angle = std::max(-1.0, std::min(1.0, cos_angle)); // Clamp
                    angle_sum += std::acos(cos_angle);
                }
            }
        }
    }
    
    // Discrete Gaussian curvature (angle defect)
    double gaussian_curvature = (2.0 * M_PI - angle_sum) / local_area;
    
    // Rough approximation: mean curvature ≈ sqrt(|Gaussian curvature|)
    // For more accuracy, you'd need principal curvatures
    return std::sqrt(std::abs(gaussian_curvature));
}


/**
 * @brief Computes a curvature-aware target edge length for adaptive remeshing.
 * 
 * This function estimates a suitable target edge length for remeshing by:
 * - Computing the bounding box of the input mesh to estimate global scale.
 * - Estimating the average curvature of the surface using mean curvature.
 * - Deriving an average radius of curvature and using it to compute the edge 
 *   length corresponding to a relative density of 2.0 (as in Houdini), 
 *   assuming the surface locally resembles a sphere covered with ~32 points.
 * 
 * This approach adapts the edge length to both the scale and the geometric complexity 
 * of the model, allowing for more detail in high-curvature regions.
 * 
 * @param mesh The input mesh (const reference).
 * @return double The computed target edge length for remeshing.
 */
double compute_target_length(const Mesh& mesh)
{
    // Compute bounding box manually
    Point min_pt(std::numeric_limits<double>::max(),
                 std::numeric_limits<double>::max(),
                 std::numeric_limits<double>::max());
    Point max_pt(std::numeric_limits<double>::lowest(),
               std::numeric_limits<double>::lowest(),
               std::numeric_limits<double>::lowest());

    for (auto v : mesh.vertices())
    {
        const Point& p = mesh.point(v);
        for (int i = 0; i < 3; ++i)
        {
            if (p[i] < min_pt[i]) min_pt = Point(
                i == 0 ? p[i] : min_pt[0],
                i == 1 ? p[i] : min_pt[1],
                i == 2 ? p[i] : min_pt[2]
            );
            if (p[i] > max_pt[i]) max_pt = Point(
                i == 0 ? p[i] : max_pt[0],
                i == 1 ? p[i] : max_pt[1],
                i == 2 ? p[i] : max_pt[2]
            );
        }
    }

    // Compute diagonal length
    CGAL::Vector_3<Kernel> diag = max_pt - min_pt;
    double diag_length = std::sqrt(diag.squared_length());

    // Estimate average mean curvature
    double total_k = 0.0;
    int count = 0;
    
    for (auto v : mesh.vertices()) {
        double k = estimate_mean_curvature(v, mesh);
        if (std::isfinite(k) && k > 1e-10) {
            total_k += k;
            ++count;
        }
    }

    double avg_k = (count > 0) ? total_k / count : 1e-8;
    double radius = (avg_k > 1e-8) ? 1.0 / avg_k : diag_length * 0.1;

    double target_len = edge_length_from_density(2.0, radius);

    return target_len;
}


/**
 * Performs adaptive isotropic remeshing on a mesh with quality validation.
 * 
 * This function applies CGAL's adaptive sizing field remeshing algorithm,
 * which adjusts edge lengths based on local curvature and geometric features.
 * After remeshing, it computes the Hausdorff distance to measure deviation
 * from the original mesh.
 * 
 * @param mesh The mesh to be remeshed (modified in-place)
 * @param original_mesh The original mesh used for distance computation
 * @param tol Tolerance for the adaptive sizing field (controls edge length variation)
 * @param target_length Target edge length used as reference for min/max bounds
 * @return The approximate Hausdorff distance between original and remeshed mesh
 */
double adaptive_isotropic_remesh(Mesh& mesh, Mesh& original_mesh, double tol = 1.0, double target_length = 1.0)
{
    double min_edge = target_length / 50.0;
    double max_edge = target_length * 5.0;

    const std::pair edge_min_max{min_edge, max_edge};

    PMP::Adaptive_sizing_field<Mesh> sizing_field(tol, edge_min_max, faces(mesh), mesh);

    PMP::isotropic_remeshing(
        faces(mesh),
        sizing_field,
        mesh,
        PMP::parameters::number_of_iterations(4)
                       .number_of_relaxation_steps(4)
    );

    std::cout << "Remeshing completed: " << num_vertices(mesh)
              << " vertices, " << num_faces(mesh) << " faces.\n";
    
    double hausdorff_dist = PMP::approximate_Hausdorff_distance<TAG>(
        original_mesh,
        mesh, 
        PMP::parameters::number_of_points_per_area_unit(4000)
    );
    std::cout << "Approximate Hausdorff distance: " << hausdorff_dist << std::endl;

    return hausdorff_dist;
}

/**
 * Main function: Performs adaptive remeshing with automatic tolerance adjustment.
 * 
 * Usage: ./adaptive_remesh input.obj output.obj tolerance
 * 
 * The program:
 * 1. Loads an input triangle mesh
 * 2. Computes the average edge length
 * 3. Applies adaptive isotropic remeshing
 * 4. If Hausdorff distance exceeds target length, retries with tighter tolerance
 * 5. Saves the remeshed output
 */
int main(int argc, char** argv)
{
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " input.obj output.obj\n";
        return EXIT_FAILURE;
    }

    std::string input_filename = argv[1];
    std::string output_filename = argv[2];

    Mesh mesh;
    if (!PMP::IO::read_polygon_mesh(input_filename, mesh) ||
        CGAL::is_empty(mesh) || !CGAL::is_triangle_mesh(mesh)) {
        std::cerr << "Error: file " << input_filename << " is not a valid triangle mesh.\n";
        return EXIT_FAILURE;
    }

    std::cout << "Mesh loaded with " << num_vertices(mesh) << " vertices and "
              << num_faces(mesh) << " faces.\n";

    Mesh original_mesh = mesh;

    const double target_length = compute_target_length(mesh);
    std::cout << "Average edge length: " << target_length << std::endl;

    double tol = target_length / 30;
    double hausdorff_dist = 0.0;
    hausdorff_dist = adaptive_isotropic_remesh(mesh, original_mesh, tol, target_length);
    
    if (hausdorff_dist > target_length/2.0) {
        tol /= 2;
        mesh = original_mesh;
        std::cout << "Retrying with tighter tolerance: " << tol << std::endl;
        hausdorff_dist = adaptive_isotropic_remesh(mesh, original_mesh, tol, target_length);
    }

    if (!CGAL::IO::write_polygon_mesh(output_filename, mesh)) {
        std::cerr << "Error writing " << output_filename << "\n";
        return EXIT_FAILURE;
    }

    std::cout << "Mesh saved to: " << output_filename << "\n";
    return EXIT_SUCCESS;
}