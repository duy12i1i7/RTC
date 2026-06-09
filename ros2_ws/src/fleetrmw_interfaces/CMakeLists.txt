cmake_minimum_required(VERSION 3.8)
project(fleetrmw_interfaces)

find_package(ament_cmake REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(sensor_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/SampleIdentity.msg"
  "msg/ProjectionQuality.msg"
  "msg/QualifiedOdometry.msg"
  "msg/QualifiedLaserScan.msg"
  DEPENDENCIES nav_msgs sensor_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
