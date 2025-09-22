cmake_minimum_required(VERSION 3.16)
project(MyRemeshTool LANGUAGES CXX)

# Impostazioni standard C++
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Ottimizzazioni di build
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG -march=native")
set(CMAKE_CXX_FLAGS_DEBUG "-g -O0")

# Trova i pacchetti necessari
find_package(PkgConfig QUIET)
find_package(pmp REQUIRED)
find_package(OpenMP REQUIRED)
find_package(CGAL REQUIRED)
find_package(TBB REQUIRED)

# Trova Eigen3 con il metodo moderno
find_package(Eigen3 3.3 REQUIRED NO_MODULE)

# Definizioni per CGAL
add_definitions(-DCGAL_LINKED_WITH_TBB)

# Crea l'eseguibile
add_executable(remesh remesh.cpp)

# Imposta le proprietà del target
set_target_properties(remesh PROPERTIES
    CXX_STANDARD 17
    CXX_STANDARD_REQUIRED ON
    CXX_EXTENSIONS OFF
)

# Link delle librerie con approccio moderno
target_link_libraries(remesh PRIVATE 
    pmp
    OpenMP::OpenMP_CXX 
    CGAL::CGAL 
    TBB::tbb
    Eigen3::Eigen
)

# Ottimizzazioni aggiuntive per il linking
if(CMAKE_BUILD_TYPE STREQUAL "Release")
    target_link_options(remesh PRIVATE -s)  # Strip symbols
endif()

# Abilita parallel make se disponibile
include(ProcessorCount)
ProcessorCount(N)
if(NOT N EQUAL 0)
    set(CMAKE_BUILD_PARALLEL_LEVEL ${N})
endif()