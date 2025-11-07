#include <iostream>
#include <vector>
#include <algorithm>
#include <cmath>

#include <Eigen/Core>

#include <utility>

#include <pmp/surface_mesh.h>
#include <pmp/algorithms/remeshing.h>
#include <pmp/algorithms/curvature.h>
#include <pmp/algorithms/decimation.h>
#include <pmp/algorithms/triangulation.h>
#include <pmp/io/io.h> 

#include </opt/nanoflann/include/nanoflann.hpp>

#include <CGAL/Simple_cartesian.h>
#include <CGAL/Surface_mesh.h>
#include <CGAL/Polygon_mesh_processing/distance.h>

namespace PMP = CGAL::Polygon_mesh_processing;
using namespace pmp;

#define TAG CGAL::Parallel_if_available_tag


// ----- KD-tree adaptor per nanoflann -----
struct PointCloudAdaptor
{
    const std::vector<Point>& pts;

    PointCloudAdaptor(const std::vector<Point>& points) : pts(points) {}

    inline size_t kdtree_get_point_count() const { return pts.size(); }

    inline float kdtree_get_pt(const size_t idx, const size_t dim) const
    {
        if (dim == 0) return pts[idx][0];
        else if (dim == 1) return pts[idx][1];
        else return pts[idx][2];
    }

    template <class BBOX>
    bool kdtree_get_bbox(BBOX& /*bb*/) const { return false; }
};

typedef nanoflann::KDTreeSingleIndexAdaptor<
    nanoflann::L2_Simple_Adaptor<float, PointCloudAdaptor>,
    PointCloudAdaptor,
    3 /* dimension */
> kd_tree_t;


/**
 * @brief Perform adaptive remeshing on a mesh.
 * 
 * This function refines the mesh by adaptively adjusting edge lengths to 
 * approximate the target edge length over a given number of iterations.
 * 
 * @param mesh Reference to the SurfaceMesh object to be remeshed.
 * @param target_edge_length Desired target length for edges after remeshing.
 * @param iterations Number of remeshing iterations to perform.
 */
void perform_remesh(SurfaceMesh& mesh, unsigned int iterations = 3, bool use_projection = false, double min_edge_length = 0.05, double max_edge_length = 4, double approximation_error = 0.01)
{
    adaptive_remeshing(mesh,
                       min_edge_length,
                       max_edge_length,
                       approximation_error,
                       iterations,
                       use_projection);
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
 * @param mesh The input mesh (must be non-const, as curvature properties are added).
 * @return double The computed target edge length for remeshing.
 */
double compute_target_length(SurfaceMesh& mesh)
{
    // Compute bounding box manually
    pmp::Point min_pt(std::numeric_limits<float>::max(),
                      std::numeric_limits<float>::max(),
                      std::numeric_limits<float>::max());
    pmp::Point max_pt(std::numeric_limits<float>::lowest(),
                      std::numeric_limits<float>::lowest(),
                      std::numeric_limits<float>::lowest());

    for (auto v : mesh.vertices())
    {
        const auto& p = mesh.position(v);
        for (int i = 0; i < 3; ++i)
        {
            min_pt[i] = std::min(min_pt[i], p[i]);
            max_pt[i] = std::max(max_pt[i], p[i]);
        }
    }

    // Diagonal vector
    pmp::Point diag = max_pt - min_pt;

    // Euclidean length of diag = sqrt(x^2 + y^2 + z^2)
    double diag_length = std::sqrt(
        double(diag[0])*diag[0] +
        double(diag[1])*diag[1] +
        double(diag[2])*diag[2]
    );

    curvature(mesh, pmp::Curvature::Mean, 0, true, false);

    auto prop = mesh.get_vertex_property<float>("v:curv");

    double total_k = 0.0;
    int count = 0;
    for (auto v : mesh.vertices()) {
        double k = std::abs(prop[v]);
        if (std::isfinite(k)) {
            total_k += k;
            ++count;
        }
    }

    double avg_k = total_k / count;
    double radius = (avg_k > 1e-8) ? 1.0 / avg_k : 1.0;

    double target_len = edge_length_from_density(2.0, radius);

    return target_len;
}


typedef CGAL::Simple_cartesian<double> Kernel;
typedef Kernel::Point_3 Point_3;
typedef CGAL::Surface_mesh<Point_3> CGALMesh;


/**
 * @brief Converts a pmp::SurfaceMesh to a CGALMesh.
 *
 * This function takes a mesh represented by `pmp::SurfaceMesh` and converts it into 
 * a `CGALMesh`, which is typically a `CGAL::Surface_mesh<Point_3>`. It does so by 
 * copying each vertex and face from the input mesh into a new CGAL-compatible mesh.
 *
 * Vertices are copied in the same order, and faces are added only if they are triangles.
 *
 * @param mesh The input mesh of type `pmp::SurfaceMesh` to be converted.
 * @return A new `CGALMesh` containing the geometry and topology of the input mesh.
 *
 * @note Only triangular faces are added to the resulting mesh. Non-triangular faces
 *       are silently ignored.
 */
CGALMesh convert_to_cgal(pmp::SurfaceMesh& mesh) {
    CGALMesh cgal_mesh;
    std::vector<CGALMesh::Vertex_index> v_indices;

    for (auto v : mesh.vertices()) {
        auto p = mesh.position(v);
        v_indices.push_back(cgal_mesh.add_vertex(Point_3(p[0], p[1], p[2])));
    }

    for (auto f : mesh.faces()) {
        std::vector<CGALMesh::Vertex_index> face;
        for (auto v : mesh.vertices(f)) {
            face.push_back(v_indices[v.idx()]);
        }
        if (face.size() == 3)
            cgal_mesh.add_face(face[0], face[1], face[2]);
    }

    return cgal_mesh;
}



/**
 * @brief Computes the bidirectional approximate Hausdorff distance between two surface meshes.
 *
 * This function estimates the Hausdorff distance between two meshes by converting them
 * to CGAL surface meshes and using CGAL's `approximate_Hausdorff_distance` function in both directions.
 * The result is the maximum of the two directed distances, ensuring a symmetric measurement.
 *
 * The computation uses a sampling strategy based on a fixed number of points per area unit
 * to balance accuracy and performance.
 *
 * @param original_mesh The first mesh (typically the high-resolution reference mesh).
 * @param working_mesh The second mesh (typically the simplified or remeshed version).
 * @return The approximate Hausdorff distance between the two meshes.
 *
 * @note This is an approximation. The accuracy depends on the `number_of_points_per_area_unit` parameter.
 */
double hausdorff_distance(pmp::SurfaceMesh& original_mesh, pmp::SurfaceMesh& working_mesh) {
    CGALMesh m1 = convert_to_cgal(original_mesh);
    CGALMesh m2 = convert_to_cgal(working_mesh);

    double dist12 = PMP::approximate_Hausdorff_distance<TAG>(m1, m2, CGAL::parameters::number_of_points_per_area_unit(1000));
    double dist21 = PMP::approximate_Hausdorff_distance<TAG>(m2, m1, CGAL::parameters::number_of_points_per_area_unit(1000));

    return std::max(dist12, dist21);
}



/**
 * @brief Attempts to remesh a mesh while controlling the Hausdorff distance to the original.
 *
 * This function tries to remesh the input mesh up to a maximum number of attempts,
 * each time reducing the target edge length if the approximation error (measured as Hausdorff distance)
 * exceeds a specified tolerance. The remeshing is considered successful if the Hausdorff distance
 * between the remeshed mesh and the original mesh is below a tolerance threshold.
 *
 * The remeshing parameters (edge lengths, projection usage, approximation error) are derived
 * from the target edge length, which is adjusted iteratively.
 *
 * @param working_mesh The mesh to be remeshed. It will be overwritten during the process.
 * @param original_mesh The original reference mesh used for computing the Hausdorff distance.
 * @param max_attempts The maximum number of remeshing attempts (default is 3).
 * @return True if a remeshed mesh satisfying the Hausdorff distance tolerance was found; false otherwise.
 *
 * @note This function assumes that `compute_target_length`, `perform_remesh`, and `hausdorff_distance`
 *       are implemented elsewhere and operate consistently with `pmp::SurfaceMesh`.
 */
bool remesh_with_control(pmp::SurfaceMesh& working_mesh, pmp::SurfaceMesh& original_mesh, int max_attempts = 3)
{
    double target_edge_length = compute_target_length(original_mesh);
    double approximation_error = target_edge_length / 30.0f;
    float dist_tolerance = target_edge_length / 2;

    float min_edge_length = target_edge_length / 20.0f;
    float max_edge_length = target_edge_length * 2.0f;
    unsigned int iterations = 2;
    bool use_projection = true;

    for (int attempt = 0; attempt < max_attempts; ++attempt)
    {
        working_mesh = original_mesh;

        perform_remesh(working_mesh, iterations, use_projection, min_edge_length, max_edge_length, approximation_error);

        double hausdorff = hausdorff_distance(original_mesh, working_mesh);

        std::cout << "--> hausdorff = " << hausdorff << std::endl;

        if (hausdorff <= dist_tolerance)
        {
            return true; // success
        }

        min_edge_length *= 0.5f;
        max_edge_length *= 0.5f;
    }

    return false; // failed all attempts
}


/**
 * @brief Main entry point of the mesh processing application.
 * 
 * This program reads an input mesh file, performs adaptive remeshing, optionally decimates
 * the mesh, and writes the resulting mesh to an output file.
 * 
 * Usage:
 * @code
 * ./program input_mesh.obj output_mesh.obj [decimate-value]
 * @endcode
 * 
 * - input_mesh.obj: path to the input mesh file (OBJ format).
 * - output_mesh.obj: path to save the processed mesh.
 * - decimate (optional): set to '1' to enable decimation, '0' or omit to disable.
 * 
 * @param argc Number of command line arguments.
 * @param argv Array of command line argument strings.
 * @return int Returns 0 on success, non-zero on failure.
 */
int main(int argc, char** argv)
{
    if (argc < 3)
    {
        std::cerr << "Usage: " << argv[0] << " input_mesh.obj output_mesh.obj\n";
        return 1;
    }

    std::string input_file = argv[1];
    std::string output_file = argv[2];

    SurfaceMesh original_mesh, working_mesh;
    try {
        read(original_mesh, input_file);
    } catch (const pmp::IOException& e) {
        std::cerr << "❌ Failed to read mesh: " << e.what() << "\n";
        return 1;
    }

    // try {
    //     triangulate(original_mesh);
    // } catch (const pmp::InvalidInputException& e) {
    //     std::cerr << "❌ Triangulation failed: " << e.what() << "\n";
    //     return 1;
    // }

    remesh_with_control(working_mesh, original_mesh, 3);

    write(working_mesh, output_file);
    std::cout << "----> Mesh processed and saved to " << output_file << "\n";

    return 0;
}
