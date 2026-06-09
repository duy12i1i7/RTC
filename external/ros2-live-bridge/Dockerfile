ARG ROS_IMAGE=ros:jazzy-ros-base
FROM ${ROS_IMAGE}

SHELL ["/bin/bash", "-lc"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        iproute2 \
        iputils-ping \
        build-essential \
        cmake \
        python3-colcon-common-extensions \
        python3-pip \
        ros-jazzy-geometry-msgs \
        ros-jazzy-nav-msgs \
        ros-jazzy-rmw-cyclonedds-cpp \
        ros-jazzy-rosidl-default-generators \
        ros-jazzy-rosidl-default-runtime \
        ros-jazzy-sensor-msgs \
        ros-jazzy-std-msgs \
    && rm -rf /var/lib/apt/lists/*

# rmw_zenoh may not be available in every ROS apt snapshot. Keep the image
# build usable and let the matrix runner report unavailable RMWs at execution.
RUN apt-get update \
    && (apt-get install -y --no-install-recommends ros-jazzy-rmw-zenoh-cpp || true) \
    && rm -rf /var/lib/apt/lists/*

COPY ros2_ws/src/fleetrmw_interfaces /opt/fleetrmw_ws/src/fleetrmw_interfaces
RUN source /opt/ros/jazzy/setup.bash \
    && colcon --log-base /opt/fleetrmw_ws/log build \
        --base-paths /opt/fleetrmw_ws/src \
        --build-base /opt/fleetrmw_ws/build \
        --install-base /opt/fleetrmw_ws/install \
        --packages-select fleetrmw_interfaces

WORKDIR /work
ENV PYTHONPATH=/work

ENTRYPOINT ["/bin/bash", "-lc"]
