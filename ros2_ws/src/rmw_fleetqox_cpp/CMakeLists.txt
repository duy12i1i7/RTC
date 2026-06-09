cmake_minimum_required(VERSION 3.8)
project(rmw_fleetqox_cpp)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(rcl REQUIRED)
find_package(rcutils REQUIRED)
find_package(rmw REQUIRED)
find_package(rosidl_runtime_c REQUIRED)
find_package(rosidl_typesupport_c REQUIRED)
find_package(rosidl_typesupport_introspection_c REQUIRED)
find_package(std_msgs REQUIRED)
find_package(std_srvs REQUIRED)

add_library(${PROJECT_NAME}_transport
  src/data_frame.cpp
)
set_target_properties(${PROJECT_NAME}_transport PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_compile_features(${PROJECT_NAME}_transport PUBLIC cxx_std_17)
target_include_directories(${PROJECT_NAME}_transport PUBLIC
  "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
  "$<INSTALL_INTERFACE:include>"
)

add_library(${PROJECT_NAME} SHARED
  src/rmw_identifier.cpp
  src/rmw_graph.cpp
  src/rmw_lifecycle.cpp
  src/rmw_pubsub.cpp
  src/rmw_stubs.cpp
  src/rmw_wait.cpp
)
target_compile_features(${PROJECT_NAME} PUBLIC cxx_std_17)
target_link_libraries(${PROJECT_NAME}
  ${PROJECT_NAME}_transport
)
ament_target_dependencies(${PROJECT_NAME}
  rcutils
  rmw
  rosidl_runtime_c
  rosidl_typesupport_c
  rosidl_typesupport_introspection_c
)

add_executable(fleetrmw_transport_loop_smoke
  src/transport_loop_smoke.cpp
)
target_compile_features(fleetrmw_transport_loop_smoke PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_transport_loop_smoke
  ${PROJECT_NAME}_transport
)

add_executable(fleetrmw_frame_probe
  src/frame_probe.cpp
)
target_compile_features(fleetrmw_frame_probe PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_frame_probe
  ${PROJECT_NAME}_transport
)

add_executable(fleetrmw_lifecycle_probe
  src/lifecycle_probe.cpp
)
target_compile_features(fleetrmw_lifecycle_probe PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_lifecycle_probe
  ${PROJECT_NAME}
)
ament_target_dependencies(fleetrmw_lifecycle_probe
  rcutils
  rmw
)

add_executable(fleetrmw_serialized_pubsub_probe
  src/serialized_pubsub_probe.cpp
)
target_compile_features(fleetrmw_serialized_pubsub_probe PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_serialized_pubsub_probe
  ${PROJECT_NAME}
)
ament_target_dependencies(fleetrmw_serialized_pubsub_probe
  rcutils
  rmw
)

add_executable(fleetrmw_qos_probe
  src/qos_probe.cpp
)
target_compile_features(fleetrmw_qos_probe PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_qos_probe
  ${PROJECT_NAME}
)
ament_target_dependencies(fleetrmw_qos_probe
  rcutils
  rmw
)

add_executable(fleetrmw_reliability_probe
  src/reliability_probe.cpp
)
target_compile_features(fleetrmw_reliability_probe PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_reliability_probe
  ${PROJECT_NAME}
)
ament_target_dependencies(fleetrmw_reliability_probe
  rcutils
  rmw
)

add_executable(fleetrmw_reliable_interprocess_probe
  src/reliable_interprocess_probe.cpp
)
target_compile_features(fleetrmw_reliable_interprocess_probe PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_reliable_interprocess_probe
  ${PROJECT_NAME}
)
ament_target_dependencies(fleetrmw_reliable_interprocess_probe
  rcutils
  rmw
)

add_executable(fleetrmw_typed_pubsub_probe
  src/typed_pubsub_probe.cpp
)
target_compile_features(fleetrmw_typed_pubsub_probe PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_typed_pubsub_probe
  ${PROJECT_NAME}
)
ament_target_dependencies(fleetrmw_typed_pubsub_probe
  rcutils
  rmw
)

add_executable(fleetrmw_std_msgs_string_probe
  src/std_msgs_string_probe.cpp
)
target_compile_features(fleetrmw_std_msgs_string_probe PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_std_msgs_string_probe
  ${PROJECT_NAME}
  std_msgs::std_msgs__rosidl_typesupport_introspection_c
)
ament_target_dependencies(fleetrmw_std_msgs_string_probe
  rcutils
  rmw
  std_msgs
)

add_executable(fleetrmw_geometry_twist_probe
  src/geometry_twist_probe.cpp
)
target_compile_features(fleetrmw_geometry_twist_probe PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_geometry_twist_probe
  ${PROJECT_NAME}
  geometry_msgs::geometry_msgs__rosidl_typesupport_introspection_c
)
ament_target_dependencies(fleetrmw_geometry_twist_probe
  geometry_msgs
  rcutils
  rmw
)

add_executable(fleetrmw_rcl_string_probe
  src/rcl_string_probe.cpp
)
target_compile_features(fleetrmw_rcl_string_probe PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_rcl_string_probe
  std_msgs::std_msgs__rosidl_typesupport_introspection_c
)
ament_target_dependencies(fleetrmw_rcl_string_probe
  rcl
  rcutils
  std_msgs
)

add_executable(fleetrmw_rcl_graph_talker
  src/rcl_graph_talker.cpp
)
target_compile_features(fleetrmw_rcl_graph_talker PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_rcl_graph_talker
  std_msgs::std_msgs__rosidl_typesupport_introspection_c
)
ament_target_dependencies(fleetrmw_rcl_graph_talker
  rcl
  rcutils
  std_msgs
)

add_executable(fleetrmw_rcl_service_node
  src/rcl_service_node.cpp
)
target_compile_features(fleetrmw_rcl_service_node PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_rcl_service_node
  std_srvs::std_srvs__rosidl_typesupport_introspection_c
)
ament_target_dependencies(fleetrmw_rcl_service_node
  rcl
  rcutils
  std_srvs
)

add_executable(fleetrmw_wait_probe
  src/wait_probe.cpp
)
target_compile_features(fleetrmw_wait_probe PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_wait_probe
  ${PROJECT_NAME}
)
ament_target_dependencies(fleetrmw_wait_probe
  rcutils
  rmw
)

add_executable(fleetrmw_graph_probe
  src/graph_probe.cpp
)
target_compile_features(fleetrmw_graph_probe PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_graph_probe
  ${PROJECT_NAME}
)
ament_target_dependencies(fleetrmw_graph_probe
  rcutils
  rmw
)

add_executable(fleetrmw_interprocess_pubsub_probe
  src/interprocess_pubsub_probe.cpp
)
target_compile_features(fleetrmw_interprocess_pubsub_probe PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_interprocess_pubsub_probe
  ${PROJECT_NAME}
)
ament_target_dependencies(fleetrmw_interprocess_pubsub_probe
  rcutils
  rmw
)

add_executable(fleetrmw_udp_router_probe
  src/udp_router_probe.cpp
)
target_compile_features(fleetrmw_udp_router_probe PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_udp_router_probe
  ${PROJECT_NAME}_transport
)

add_executable(fleetrmw_remote_graph_probe
  src/remote_graph_probe.cpp
)
target_compile_features(fleetrmw_remote_graph_probe PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_remote_graph_probe
  ${PROJECT_NAME}
)
ament_target_dependencies(fleetrmw_remote_graph_probe
  rcutils
  rmw
)

add_executable(fleetrmw_remote_graph_lease_probe
  src/remote_graph_lease_probe.cpp
)
target_compile_features(fleetrmw_remote_graph_lease_probe PRIVATE cxx_std_17)
target_link_libraries(fleetrmw_remote_graph_lease_probe
  ${PROJECT_NAME}
)
ament_target_dependencies(fleetrmw_remote_graph_lease_probe
  rcutils
  rmw
)

install(
  DIRECTORY include/
  DESTINATION include
)
install(
  TARGETS
    ${PROJECT_NAME}
    ${PROJECT_NAME}_transport
    fleetrmw_transport_loop_smoke
    fleetrmw_frame_probe
    fleetrmw_lifecycle_probe
    fleetrmw_serialized_pubsub_probe
    fleetrmw_qos_probe
    fleetrmw_reliability_probe
    fleetrmw_reliable_interprocess_probe
    fleetrmw_typed_pubsub_probe
    fleetrmw_std_msgs_string_probe
    fleetrmw_geometry_twist_probe
    fleetrmw_rcl_string_probe
    fleetrmw_rcl_graph_talker
    fleetrmw_rcl_service_node
    fleetrmw_wait_probe
    fleetrmw_graph_probe
    fleetrmw_interprocess_pubsub_probe
    fleetrmw_udp_router_probe
    fleetrmw_remote_graph_probe
    fleetrmw_remote_graph_lease_probe
  EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)

ament_export_include_directories(include)
ament_export_libraries(${PROJECT_NAME} ${PROJECT_NAME}_transport)
ament_export_targets(export_${PROJECT_NAME})
register_rmw_implementation("c:rosidl_typesupport_introspection_c")
ament_package()
