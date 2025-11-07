cmake_minimum_required(VERSION 3.10)
project(adaptive_remesh)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ============================================================================
# CONFIGURAZIONE BUILD TYPE
# ============================================================================
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")

# ============================================================================
# FLAGS DI OTTIMIZZAZIONE
# ============================================================================
if(CMAKE_BUILD_TYPE MATCHES Release)
    # Ottimizzazioni aggressive per Release
    set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG")
    
    add_compile_options(
        -O3                     # Massima ottimizzazione
        -march=native           # Ottimizza per CPU corrente
        -mtune=native           # Tuning per CPU corrente
        -ffast-math             # Ottimizzazioni matematiche aggressive
        -funroll-loops          # Unroll dei loop
        -finline-functions      # Inline aggressivo
    )
    
    # Link-Time Optimization (LTO)
    set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)
    message(STATUS "Link-Time Optimization: ENABLED")
    
    # Ottimizzazioni specifiche per GCC
    if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
        add_compile_options(
            -ftree-vectorize    # Vettorizzazione automatica
            -fomit-frame-pointer
        )
    endif()
    
    # Ottimizzazioni specifiche per Clang
    if(CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
        add_compile_options(
            -fvectorize
        )
    endif()
endif()

# ============================================================================
# TROVA DIPENDENZE
# ============================================================================

# Trova CGAL e componenti necessari
find_package(CGAL REQUIRED COMPONENTS Core)

# Trova Eigen3
find_package(Eigen3 3.3 REQUIRED NO_MODULE)

# Trova TBB per il parallelismo
find_package(TBB)

# OpenMP (alternativa/complementare a TBB)
find_package(OpenMP)

# ============================================================================
# CONFIGURAZIONE CGAL
# ============================================================================

# Disabilita assertion di CGAL in Release per prestazioni massime
if(CMAKE_BUILD_TYPE MATCHES Release)
    add_definitions(-DCGAL_NDEBUG)
    message(STATUS "CGAL assertions: DISABLED (for performance)")
endif()

# ============================================================================
# CREAZIONE ESEGUIBILE
# ============================================================================

add_executable(adaptive_remesh adaptive_remesh.cpp)

# ============================================================================
# LINKING LIBRERIE
# ============================================================================

# Collega le librerie principali
target_link_libraries(adaptive_remesh
    CGAL::CGAL
    CGAL::CGAL_Core
    Eigen3::Eigen
)

# TBB per multithreading CGAL
if(TBB_FOUND)
    message(STATUS "TBB: FOUND — Multithreading CGAL abilitato")
    target_link_libraries(adaptive_remesh TBB::tbb)
    target_compile_definitions(adaptive_remesh PRIVATE CGAL_LINKED_WITH_TBB)
else()
    message(WARNING "TBB: NOT FOUND — Esecuzione single-thread")
endif()

# OpenMP per parallelizzazione aggiuntiva
if(OpenMP_CXX_FOUND)
    message(STATUS "OpenMP: FOUND — Parallelizzazione abilitata")
    target_link_libraries(adaptive_remesh OpenMP::OpenMP_CXX)
else()
    message(STATUS "OpenMP: NOT FOUND")
endif()

# ============================================================================
# OTTIMIZZAZIONI EIGEN
# ============================================================================

# Eigen con vettorizzazione SIMD
target_compile_definitions(adaptive_remesh PRIVATE 
    EIGEN_NO_DEBUG                  # Disabilita check di Eigen in Release
    EIGEN_DONT_PARALLELIZE          # Evita conflitti con TBB/OpenMP
)

if(CMAKE_BUILD_TYPE MATCHES Release)
    target_compile_definitions(adaptive_remesh PRIVATE 
        EIGEN_FAST_MATH             # Ottimizzazioni matematiche Eigen
    )
endif()

# ============================================================================
# INFO DI BUILD
# ============================================================================

message(STATUS "")
message(STATUS "==================== BUILD CONFIGURATION ====================")
message(STATUS "Compiler: ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "C++ Standard: ${CMAKE_CXX_STANDARD}")
message(STATUS "Optimization flags: ${CMAKE_CXX_FLAGS_RELEASE}")
message(STATUS "LTO: ${CMAKE_INTERPROCEDURAL_OPTIMIZATION}")
message(STATUS "=============================================================")
message(STATUS "")
