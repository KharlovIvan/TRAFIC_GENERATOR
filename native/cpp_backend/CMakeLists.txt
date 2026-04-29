cmake_minimum_required(VERSION 3.20)
project(trafic_native_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(pybind11 REQUIRED)

pybind11_add_module(trafic_native
    src/bindings.cpp
    src/sender.cpp
    src/serializer.cpp
    src/testgen.cpp
    src/errors.cpp
)

target_include_directories(trafic_native PRIVATE src)
