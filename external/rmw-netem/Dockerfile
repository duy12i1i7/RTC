ARG ROS_IMAGE=ros:jazzy-ros-base
FROM ${ROS_IMAGE}

ARG AIOQUIC_DEB_VERSION=0.9.25-3build2
ARG PSYCOPG_DEB_VERSION=3.1.17-2

SHELL ["/bin/bash", "-lc"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        iproute2 \
        build-essential \
        cmake \
        libgnutls28-dev \
        libngtcp2-dev \
        libngtcp2-crypto-gnutls-dev \
        libnghttp3-dev \
        ngtcp2-client \
        ngtcp2-server \
        openssl \
        pkg-config \
        libgsl-dev \
        libns3-dev \
        libssl-dev \
        ns3 \
        python3-aioquic=${AIOQUIC_DEB_VERSION} \
        python3-psycopg=${PSYCOPG_DEB_VERSION} \
        python3-colcon-common-extensions \
        ros-jazzy-geometry-msgs \
        ros-jazzy-nav-msgs \
        ros-jazzy-nav2-behaviors \
        ros-jazzy-nav2-behavior-tree \
        ros-jazzy-nav2-bt-navigator \
        ros-jazzy-nav2-controller \
        ros-jazzy-nav2-dwb-controller \
        ros-jazzy-nav2-lifecycle-manager \
        ros-jazzy-nav2-msgs \
        ros-jazzy-nav2-navfn-planner \
        ros-jazzy-nav2-planner \
        ros-jazzy-rmf-fleet-msgs \
        ros-jazzy-rmf-task-msgs \
        ros-jazzy-rmf-traffic-msgs \
        ros-jazzy-rmw-cyclonedds-cpp \
        ros-jazzy-rosidl-default-generators \
        ros-jazzy-rosidl-default-runtime \
        ros-jazzy-sensor-msgs \
        ros-jazzy-std-msgs \
        ros-jazzy-std-srvs \
        ros-jazzy-tf2-msgs \
        ros-jazzy-tinyxml2-vendor \
    && rm -rf /var/lib/apt/lists/*

# rmw_zenoh may not be available in every ROS apt snapshot. Keep the image
# build usable and let baseline runners report unavailable RMWs at execution.
RUN apt-get update \
    && (apt-get install -y --no-install-recommends ros-jazzy-rmw-zenoh-cpp || true) \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
ENV PYTHONPATH=/work

ENTRYPOINT ["/bin/bash", "-lc"]
