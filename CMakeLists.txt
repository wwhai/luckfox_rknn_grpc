cmake_minimum_required(VERSION 3.16)
project(luckfox_rknn_grpc VERSION 0.2.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_INSTALL_RPATH "$ORIGIN/lib")

set(RKNN_EXAMPLE_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../luckfox_pico_rknn_example"
    CACHE PATH "Path to luckfox_pico_rknn_example")
set(GRPC_TARGET_PREFIX "${CMAKE_CURRENT_SOURCE_DIR}/.deps/target"
    CACHE PATH "Target gRPC installation prefix")
set(HOST_PROTOC "${CMAKE_CURRENT_SOURCE_DIR}/.deps/host/bin/protoc"
    CACHE FILEPATH "Host protoc executable")
set(HOST_GRPC_CPP_PLUGIN "${CMAKE_CURRENT_SOURCE_DIR}/.deps/host/bin/grpc_cpp_plugin"
    CACHE FILEPATH "Host grpc_cpp_plugin executable")

foreach(required_path RKNN_EXAMPLE_ROOT GRPC_TARGET_PREFIX HOST_PROTOC HOST_GRPC_CPP_PLUGIN)
    if(NOT EXISTS "${${required_path}}")
        message(FATAL_ERROR "${required_path} does not exist: ${${required_path}}")
    endif()
endforeach()

list(PREPEND CMAKE_PREFIX_PATH "${GRPC_TARGET_PREFIX}")
find_package(Protobuf CONFIG REQUIRED)
find_package(gRPC CONFIG REQUIRED)
find_package(Threads REQUIRED)

set(OpenCV_DIR "${RKNN_EXAMPLE_ROOT}/lib/uclibc/lib/cmake/opencv4")
find_package(OpenCV REQUIRED)

set(PROTO_FILE "${CMAKE_CURRENT_SOURCE_DIR}/proto/rknn_accelerator.proto")
set(GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
set(PROTO_SOURCE "${GENERATED_DIR}/rknn_accelerator.pb.cc")
set(PROTO_HEADER "${GENERATED_DIR}/rknn_accelerator.pb.h")
set(GRPC_SOURCE "${GENERATED_DIR}/rknn_accelerator.grpc.pb.cc")
set(GRPC_HEADER "${GENERATED_DIR}/rknn_accelerator.grpc.pb.h")

add_custom_command(
    OUTPUT "${PROTO_SOURCE}" "${PROTO_HEADER}" "${GRPC_SOURCE}" "${GRPC_HEADER}"
    COMMAND "${CMAKE_COMMAND}" -E make_directory "${GENERATED_DIR}"
    COMMAND "${HOST_PROTOC}"
            "--proto_path=${CMAKE_CURRENT_SOURCE_DIR}/proto"
            "--cpp_out=${GENERATED_DIR}"
            "--grpc_out=${GENERATED_DIR}"
            "--plugin=protoc-gen-grpc=${HOST_GRPC_CPP_PLUGIN}"
            "${PROTO_FILE}"
    DEPENDS "${PROTO_FILE}"
    VERBATIM)

add_library(accelerator_proto STATIC "${PROTO_SOURCE}" "${GRPC_SOURCE}")
target_include_directories(accelerator_proto PUBLIC "${GENERATED_DIR}")
target_link_libraries(accelerator_proto PUBLIC gRPC::grpc++ protobuf::libprotobuf)

find_library(RKNN_RUNTIME rknnmrt
    PATHS "${RKNN_EXAMPLE_ROOT}/lib/uclibc"
    NO_DEFAULT_PATH REQUIRED)

add_executable(rknn_grpc_server
    server/src/main.cc
    server/src/grpc_server.cc
    server/src/discovery_service.cc
    server/src/system_metrics.cc
    server/src/session_store.cc
    server/src/accelerator_engine.cc
    "${RKNN_EXAMPLE_ROOT}/example/luckfox_pico_yolov5/src/yolov5.cc"
    "${RKNN_EXAMPLE_ROOT}/example/luckfox_pico_yolov5/src/postprocess.cc")

target_compile_definitions(rknn_grpc_server PRIVATE RV1106_1103)
target_include_directories(rknn_grpc_server PRIVATE
    server/include
    "${RKNN_EXAMPLE_ROOT}/example/luckfox_pico_yolov5/include"
    "${RKNN_EXAMPLE_ROOT}/include"
    "${RKNN_EXAMPLE_ROOT}/include/rknn"
    "${RKNN_EXAMPLE_ROOT}/utils"
    ${OpenCV_INCLUDE_DIRS})
target_link_libraries(rknn_grpc_server PRIVATE
    accelerator_proto
    ${OpenCV_LIBS}
    "${RKNN_RUNTIME}"
    Threads::Threads)

install(TARGETS rknn_grpc_server RUNTIME DESTINATION .)
install(FILES
    "${RKNN_EXAMPLE_ROOT}/example/luckfox_pico_yolov5/model/yolov5.rknn"
    "${RKNN_EXAMPLE_ROOT}/example/luckfox_pico_yolov5/model/coco_80_labels_list.txt"
    DESTINATION model)
install(FILES "${RKNN_EXAMPLE_ROOT}/lib/uclibc/librknnmrt.so" DESTINATION lib)
install(PROGRAMS deploy/start_server.sh DESTINATION .)