ARG ROS_IMAGE=ros:jazzy-ros-base
FROM ${ROS_IMAGE}

SHELL ["/bin/bash", "-lc"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        iproute2 \
        build-essential \
        cmake \
        python3-colcon-common-extensions \
        ros-jazzy-geometry-msgs \
        ros-jazzy-nav-msgs \
        ros-jazzy-rmw-cyclonedds-cpp \
        ros-jazzy-rosidl-default-generators \
        ros-jazzy-rosidl-default-runtime \
        ros-jazzy-sensor-msgs \
        ros-jazzy-std-msgs \
        ros-jazzy-std-srvs \
    && rm -rf /var/lib/apt/lists/*

# rmw_zenoh may not be available in every ROS apt snapshot. Keep the image
# build usable and let baseline runners report unavailable RMWs at execution.
RUN apt-get update \
    && (apt-get install -y --no-install-recommends ros-jazzy-rmw-zenoh-cpp || true) \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
ENV PYTHONPATH=/work

ENTRYPOINT ["/bin/bash", "-lc"]
