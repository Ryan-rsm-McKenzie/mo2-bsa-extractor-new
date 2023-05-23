cmake_minimum_required(VERSION 3.26)

project(bsa_extractor LANGUAGES CXX)

if("${CMAKE_CXX_COMPILER_ID}" MATCHES "Clang|GNU")
	set(CMAKE_CXX_EXTENSIONS OFF)
endif()

set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_subdirectory(src)
