#pragma once

#include <cstdint>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace rmw_fleetqox_cpp
{

constexpr const char * kDataFrameSchemaVersion = "fleetrmw.data_frame.v1";
constexpr const char * kAckNackSchemaVersion = "fleetrmw.ack_nack.v1";
constexpr const char * kRouteAdvertisementSchemaVersion = "fleetrmw.route_advertisement.v1";
constexpr const char * kGraphAdvertisementSchemaVersion = "fleetrmw.graph_advertisement.v1";
constexpr const char * kServiceFrameSchemaVersion = "fleetrmw.service_frame.v1";
constexpr const char * kDataFrameMagic = "FRMW1\n";

struct DataFrame
{
  std::string robot_id;
  std::string topic;
  std::string publisher_id;
  std::uint64_t source_sequence_number = 0;
  std::int64_t source_timestamp_ns = 0;
  std::vector<std::uint8_t> serialized_payload;
};

struct SequenceState
{
  bool initialized = false;
  std::uint64_t highest_contiguous_sequence = 0;
  std::uint64_t highest_observed_sequence = 0;
  std::int64_t last_repair_request_ns = 0;
  std::set<std::uint64_t> observed_sequences;
};

struct AckNackFeedback
{
  std::vector<std::pair<std::uint64_t, std::uint64_t>> missing_sequence_ranges;
  std::uint64_t highest_contiguous_sequence = 0;
  std::uint64_t highest_observed_sequence = 0;
  bool duplicate = false;
  bool out_of_order = false;
};

struct AckNackFrame
{
  std::string robot_id;
  std::string topic;
  std::string publisher_id;
  std::uint64_t ack_sequence_number = 0;
  std::int64_t source_timestamp_ns = 0;
  std::vector<std::pair<std::uint64_t, std::uint64_t>> missing_sequence_ranges;
  std::uint64_t highest_contiguous_sequence = 0;
  std::uint64_t highest_observed_sequence = 0;
  bool duplicate = false;
  bool out_of_order = false;
};

struct RouteAdvertisement
{
  std::string endpoint_id;
  std::string role;
  std::string topic;
  std::string type_name;
  std::uint64_t lease_ms = 0;
};

struct GraphQosProfile
{
  std::uint64_t history = 0;
  std::uint64_t depth = 0;
  std::uint64_t reliability = 0;
  std::uint64_t durability = 0;
  std::uint64_t deadline_sec = 0;
  std::uint64_t deadline_nsec = 0;
  std::uint64_t lifespan_sec = 0;
  std::uint64_t lifespan_nsec = 0;
  std::uint64_t liveliness = 0;
  std::uint64_t liveliness_lease_duration_sec = 0;
  std::uint64_t liveliness_lease_duration_nsec = 0;
  std::uint64_t avoid_ros_namespace_conventions = 0;
};

struct GraphAdvertisement
{
  std::string endpoint_id;
  std::string action;
  std::string entity_kind;
  std::string node_name;
  std::string node_namespace;
  std::string topic;
  std::string type_name;
  std::string endpoint_gid;
  GraphQosProfile qos;
  std::uint64_t lease_ms = 0;
};

struct ServiceFrame
{
  std::string role;
  std::string service_name;
  std::string type_name;
  std::string client_endpoint_id;
  std::string service_endpoint_id;
  std::int64_t sequence_id = 0;
  std::int64_t source_timestamp_ns = 0;
  std::int64_t lifespan_ns = 0;
  std::vector<std::uint8_t> serialized_payload;
};

std::string stream_key(const DataFrame & frame);

std::string encode_data_frame(const DataFrame & frame);

std::optional<DataFrame> decode_data_frame(const std::string & payload);

std::string encode_route_advertisement(const RouteAdvertisement & advertisement);

std::optional<RouteAdvertisement> decode_route_advertisement(const std::string & payload);

std::string encode_graph_advertisement(const GraphAdvertisement & advertisement);

std::optional<GraphAdvertisement> decode_graph_advertisement(const std::string & payload);

std::string encode_service_frame(const ServiceFrame & frame);

std::optional<ServiceFrame> decode_service_frame(const std::string & payload);

bool service_frame_expired(const ServiceFrame & frame, std::int64_t now_ns);

AckNackFeedback observe_frame(SequenceState & state, const DataFrame & frame);

AckNackFeedback feedback_from_sequence_state(const SequenceState & state);

std::string encode_ack_nack(const DataFrame & frame, const AckNackFeedback & feedback);

std::optional<AckNackFrame> decode_ack_nack(const std::string & payload);

std::vector<std::uint64_t> missing_sequences_from_ack_nack(const std::string & payload);

bool ack_nack_reports_out_of_order(const std::string & payload);

}  // namespace rmw_fleetqox_cpp
