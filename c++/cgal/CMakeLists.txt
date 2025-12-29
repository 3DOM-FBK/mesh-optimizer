cmake_minimum_required(VERSION 3.16)
project(AdaptiveRemesh LANGUAGES CXX)

# ============================================================================
# C++ Standard
# ============================================================================
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ============================================================================
# Build Type (default: Release)
# ============================================================================
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    message(STATUS "Setting build type to 'Release' as none was specified.")
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Choose the type of build." FORCE)
    set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS "Debug" "Release" "MinSizeRel" "RelWithDebInfo")
endif()

# ============================================================================
# Compiler Optimization Flags (Maximum Performance)
# ============================================================================
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    # Optimization flags for GCC/Clang
    set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG")
    
    # Architecture-specific optimizations
    include(CheckCXXCompilerFlag)
    check_cxx_compiler_flag("-march=native" COMPILER_SUPPORTS_MARCH_NATIVE)
    if(COMPILER_SUPPORTS_MARCH_NATIVE)
        set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -march=native")
    endif()
    
    # Link Time Optimization (LTO)
    check_cxx_compiler_flag("-flto" COMPILER_SUPPORTS_LTO)
    if(COMPILER_SUPPORTS_LTO)
        set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -flto")
        set(CMAKE_EXE_LINKER_FLAGS_RELEASE "${CMAKE_EXE_LINKER_FLAGS_RELEASE} -flto")
    endif()
    
    # Additional aggressive optimizations
    set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -funroll-loops -ffast-math -ftree-vectorize")
    
    # Disable runtime checks for maximum speed
    set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -fno-stack-protector -fomit-frame-pointer")
    
elseif(CMAKE_CXX_COMPILER_ID MATCHES "MSVC")
    # Optimization flags for MSVC
    set(CMAKE_CXX_FLAGS_RELEASE "/O2 /Ob3 /DNDEBUG /GL /Oi /Ot /Oy /GS- /fp:fast")
    set(CMAKE_EXE_LINKER_FLAGS_RELEASE "/LTCG")
endif()

# ============================================================================
# Find Required Packages
# ============================================================================

# CGAL (header-only in 6.x, Core component requires linking)
find_package(CGAL REQUIRED COMPONENTS Core)
if(NOT CGAL_FOUND)
    message(FATAL_ERROR "CGAL not found. Please install CGAL 6.1 or later.")
endif()
message(STATUS "Found CGAL: ${CGAL_VERSION}")

# Boost
find_package(Boost REQUIRED)
if(NOT Boost_FOUND)
    message(FATAL_ERROR "Boost not found. Please install Boost.")
endif()
message(STATUS "Found Boost: ${Boost_VERSION}")

# Eigen3 (required for Adaptive_sizing_field curvature calculations)
find_package(Eigen3 3.3 REQUIRED NO_MODULE)
if(NOT Eigen3_FOUND)
    message(FATAL_ERROR "Eigen3 not found. Please install Eigen3 3.3 or later.")
endif()
message(STATUS "Found Eigen3: ${Eigen3_VERSION}")

# OpenMP (optional, for parallel processing)
find_package(OpenMP)
if(OpenMP_CXX_FOUND)
    message(STATUS "Found OpenMP: ${OpenMP_CXX_VERSION}")
endif()

# TBB (optional, CGAL can use TBB for parallelization)
find_package(TBB QUIET)
if(TBB_FOUND)
    message(STATUS "Found TBB: using TBB for parallel algorithms")
endif()

# ============================================================================
# Executable
# ============================================================================
add_executable(remesh remesh.cpp)

# ============================================================================
# Link Libraries
# ============================================================================
target_link_libraries(remesh PRIVATE 
    CGAL::CGAL 
    CGAL::CGAL_Core 
    Boost::boost 
    Eigen3::Eigen
)

# Link OpenMP if available
if(OpenMP_CXX_FOUND)
    target_link_libraries(remesh PRIVATE OpenMP::OpenMP_CXX)
    target_compile_definitions(remesh PRIVATE CGAL_LINKED_WITH_OPENMP)
endif()

# Link TBB if available
if(TBB_FOUND)
    target_link_libraries(remesh PRIVATE TBB::tbb)
    target_compile_definitions(remesh PRIVATE CGAL_LINKED_WITH_TBB)
endif()

# ============================================================================
# Compile Definitions
# ============================================================================
target_compile_definitions(remesh PRIVATE 
    CGAL_USE_CORE
    CGAL_EIGEN3_ENABLED
    # Disable CGAL assertions in Release for speed
    $<$<CONFIG:Release>:CGAL_NDEBUG>
    # Use less precise but faster floating point
    $<$<CONFIG:Release>:CGAL_USE_SSE2_MATH>
)

# ============================================================================
# Include Directories
# ============================================================================
target_include_directories(remesh PRIVATE ${Boost_INCLUDE_DIRS})

# ============================================================================
# Installation (optional)
# ============================================================================
install(TARGETS remesh DESTINATION bin)

# ============================================================================
# Print Configuration Summary
# ============================================================================
message(STATUS "")
message(STATUS "=== Build Configuration ===")
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "CXX Compiler: ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")
message(STATUS "CXX Flags (Release): ${CMAKE_CXX_FLAGS_RELEASE}")
message(STATUS "OpenMP: ${OpenMP_CXX_FOUND}")
message(STATUS "TBB: ${TBB_FOUND}")
message(STATUS "===========================")
message(STATUS "")
