#include <CGAL/Exact_predicates_inexact_constructions_kernel.h>
#include <CGAL/Surface_mesh.h>
#include <CGAL/Polygon_mesh_processing/remesh.h>
#include <CGAL/Polygon_mesh_processing/IO/polygon_mesh_io.h>
#include <CGAL/Polygon_mesh_processing/Adaptive_sizing_field.h>
#include <CGAL/Polygon_mesh_processing/bbox.h>
#include <CGAL/Polygon_mesh_processing/border.h>

#include <boost/iterator/function_output_iterator.hpp>

#include <iostream>
#include <string>
#include <cmath>
#include <vector>

typedef CGAL::Exact_predicates_inexact_constructions_kernel Kernel;
typedef CGAL::Surface_mesh<Kernel::Point_3> Mesh;

typedef boost::graph_traits<Mesh>::halfedge_descriptor halfedge_descriptor;
typedef boost::graph_traits<Mesh>::edge_descriptor edge_descriptor;

namespace PMP = CGAL::Polygon_mesh_processing;

// Functor per convertire halfedge in edge
struct halfedge2edge
{
    halfedge2edge(const Mesh& m, std::vector<edge_descriptor>& edges)
        : m_mesh(m), m_edges(edges)
    {}
    void operator()(const halfedge_descriptor& h) const
    {
        m_edges.push_back(edge(h, m_mesh));
    }
    const Mesh& m_mesh;
    std::vector<edge_descriptor>& m_edges;
};

// Calcola la diagonale della bounding box della mesh
double compute_bbox_diagonal(const Mesh& mesh) {
    CGAL::Bbox_3 bbox = PMP::bbox(mesh);
    double dx = bbox.xmax() - bbox.xmin();
    double dy = bbox.ymax() - bbox.ymin();
    double dz = bbox.zmax() - bbox.zmin();
    return std::sqrt(dx*dx + dy*dy + dz*dz);
}

int main(int argc, char* argv[])
{
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " input.obj output.obj [tolerance] [edge_min] [edge_max] [iterations]\n";
        std::cerr << "\n";
        std::cerr << "Parameters:\n";
        std::cerr << "  input.obj   : Input mesh file (OBJ, OFF, PLY supported)\n";
        std::cerr << "  output.obj  : Output mesh file\n";
        std::cerr << "  tolerance   : Approximation tolerance for curvature adaptation (default: 0.001)\n";
        std::cerr << "  edge_min    : Minimum edge length (default: auto, 0.1% of bbox diagonal)\n";
        std::cerr << "  edge_max    : Maximum edge length (default: auto, 5% of bbox diagonal)\n";
        std::cerr << "  iterations  : Number of remeshing iterations (default: 5)\n";
        std::cerr << "\n";
        std::cerr << "Note: Border edges (mesh boundaries/holes) are automatically detected and preserved.\n";
        return EXIT_FAILURE;
    }

    // Parse arguments
    const std::string input_file = argv[1];
    const std::string output_file = argv[2];
    const double tolerance = (argc > 3) ? std::stod(argv[3]) : 0.001;
    const unsigned int nb_iterations = (argc > 6) ? std::stoi(argv[6]) : 5;

    // Load mesh
    Mesh mesh;
    if (!PMP::IO::read_polygon_mesh(input_file, mesh)) {
        std::cerr << "Error: Cannot read input file " << input_file << std::endl;
        return EXIT_FAILURE;
    }

    // Validate input mesh
    if (!CGAL::is_triangle_mesh(mesh)) {
        std::cerr << "Error: Input mesh is not a valid triangle mesh." << std::endl;
        return EXIT_FAILURE;
    }

    // Calcola edge_min e edge_max automaticamente se non specificati
    double bbox_diag = compute_bbox_diagonal(mesh);
    const double edge_min = (argc > 4) ? std::stod(argv[4]) : (bbox_diag * 0.001);  // 0.1% della diagonale
    const double edge_max = (argc > 5) ? std::stod(argv[5]) : (bbox_diag * 0.05);   // 5% della diagonale

    std::cout << "=== Adaptive Isotropic Remeshing ===" << std::endl;
    std::cout << "Input file: " << input_file << std::endl;
    std::cout << "Output file: " << output_file << std::endl;
    std::cout << "Bounding box diagonal: " << bbox_diag << std::endl;
    std::cout << "Tolerance: " << tolerance << std::endl;
    std::cout << "Edge length range: [" << edge_min << ", " << edge_max << "]" << std::endl;
    std::cout << "Iterations: " << nb_iterations << std::endl;
    std::cout << std::endl;

    std::cout << "Mesh before remeshing: " 
              << mesh.number_of_vertices() << " vertices, "
              << mesh.number_of_faces() << " faces" << std::endl;

    // ========================================================================
    // Detect and protect border edges (holes/boundaries)
    // ========================================================================
    std::vector<edge_descriptor> border_edges;
    PMP::border_halfedges(faces(mesh), mesh, 
        boost::make_function_output_iterator(halfedge2edge(mesh, border_edges)));
    
    bool has_borders = !border_edges.empty();
    if (has_borders) {
        std::cout << "Detected " << border_edges.size() << " border edges (open mesh with holes/boundaries)" << std::endl;
        
        // Split long border edges to match target edge length
        // This is important to ensure border edges can accommodate the target length
        std::cout << "Splitting long border edges..." << std::endl;
        PMP::split_long_edges(border_edges, edge_max, mesh);
        
        // Update border edges after splitting
        border_edges.clear();
        PMP::border_halfedges(faces(mesh), mesh, 
            boost::make_function_output_iterator(halfedge2edge(mesh, border_edges)));
        std::cout << "Border edges after splitting: " << border_edges.size() << std::endl;
    } else {
        std::cout << "No border edges detected (closed mesh)" << std::endl;
    }
    std::cout << std::endl;

    // ========================================================================
    // Create adaptive sizing field based on curvature
    // ========================================================================
    const std::pair<double, double> edge_min_max{edge_min, edge_max};
    PMP::Adaptive_sizing_field<Mesh> sizing_field(tolerance, edge_min_max, faces(mesh), mesh);

    std::cout << "Running adaptive isotropic remeshing..." << std::endl;

    // ========================================================================
    // Perform adaptive isotropic remeshing with border protection
    // ========================================================================
    PMP::isotropic_remeshing(
        faces(mesh),
        sizing_field,
        mesh,
        CGAL::parameters::number_of_iterations(nb_iterations)
                         .number_of_relaxation_steps(3)
                         .protect_constraints(true)  // Protects border edges from modification
    );

    std::cout << "Mesh after remeshing: " 
              << mesh.number_of_vertices() << " vertices, "
              << mesh.number_of_faces() << " faces" << std::endl;

    // ========================================================================
    // Save output mesh
    // ========================================================================
    if (!CGAL::IO::write_polygon_mesh(output_file, mesh, CGAL::parameters::stream_precision(17))) {
        std::cerr << "Error: Cannot write output file " << output_file << std::endl;
        return EXIT_FAILURE;
    }

    std::cout << std::endl;
    std::cout << "Remeshing completed successfully!" << std::endl;
    if (has_borders) {
        std::cout << "Border edges were preserved as constraints." << std::endl;
    }
    std::cout << "Output saved to: " << output_file << std::endl;

    return EXIT_SUCCESS;
}

