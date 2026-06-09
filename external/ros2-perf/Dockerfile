ARG ROS_IMAGE=osrf/ros:jazzy-desktop
FROM ${ROS_IMAGE}

SHELL ["/bin/bash", "-lc"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        python3-colcon-common-extensions \
        python3-pip \
        ros-jazzy-rmw-cyclonedds-cpp \
    && rm -rf /var/lib/apt/lists/*

# rmw_zenoh may not be available in every ROS apt snapshot. Keep the image
# build usable and let the runner report unavailable RMWs at execution time.
RUN apt-get update \
    && (apt-get install -y --no-install-recommends ros-jazzy-rmw-zenoh-cpp || true) \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/performance_test_ws/src \
    && cd /opt/performance_test_ws/src \
    && git clone --depth 1 https://gitlab.com/ApexAI/performance_test.git \
    && cd /opt/performance_test_ws \
    && source /opt/ros/jazzy/setup.bash \
    && colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release -DPERFORMANCE_TEST_PLUGIN=ROS2

RUN apt-get update \
    && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
ENV PYTHONPATH=/work

ENTRYPOINT ["/bin/bash", "-lc"]
