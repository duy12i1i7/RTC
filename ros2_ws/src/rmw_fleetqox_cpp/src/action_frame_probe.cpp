#include "rmw_fleetqox_cpp/data_frame.hpp"

#include <cstddef>
#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace
{

std::string json_escape(const std::string & value)
{
  std::ostringstream out;
  for (const char c : value) {
    if (c == '\\' || c == '"') {
      out << '\\' << c;
    } else if (c == '\n') {
      out << "\\n";
    } else {
      out << c;
    }
  }
  return out.str();
}

rmw_fleetqox_cpp::ActionFrame frame_for_role(const std::string & role, std::int64_t sequence)
{
  return rmw_fleetqox_cpp::ActionFrame{
    role,
    "/fleetqox/navigate_to_pose",
    "nav2_msgs/action/NavigateToPose",
    "action-endpoint-1",
    "goal-00112233",
    sequence,
    1000000,
    5000000,
    {static_cast<std::uint8_t>(sequence), 0xA0, 0x5A}};
}

}  // namespace

int main()
{
  const std::vector<std::string> roles{"goal", "feedback", "status", "result", "cancel"};
  std::vector<std::string> decoded_roles;
  bool roundtrip_ok = true;
  std::int64_t sequence = 1;
  for (const std::string & role : roles) {
    const rmw_fleetqox_cpp::ActionFrame frame = frame_for_role(role, sequence++);
    const std::string encoded = rmw_fleetqox_cpp::encode_action_frame(frame);
    const auto decoded = rmw_fleetqox_cpp::decode_action_frame(encoded);
    const bool matches = decoded &&
                         decoded->role == frame.role &&
                         decoded->action_name == frame.action_name &&
                         decoded->type_name == frame.type_name &&
                         decoded->endpoint_id == frame.endpoint_id &&
                         decoded->goal_id == frame.goal_id &&
                         decoded->sequence_id == frame.sequence_id &&
                         decoded->lifespan_ns == frame.lifespan_ns &&
                         decoded->serialized_payload == frame.serialized_payload;
    roundtrip_ok = roundtrip_ok && matches;
    if (decoded) {
      decoded_roles.push_back(decoded->role);
    }
  }

  const rmw_fleetqox_cpp::ActionFrame expiry_frame = frame_for_role("goal", 99);
  const bool not_expired =
    !rmw_fleetqox_cpp::action_frame_expired(
      expiry_frame,
      expiry_frame.source_timestamp_ns + expiry_frame.lifespan_ns - 1);
  const bool expired =
    rmw_fleetqox_cpp::action_frame_expired(
      expiry_frame,
      expiry_frame.source_timestamp_ns + expiry_frame.lifespan_ns + 1);
  const bool rejects_service_schema = !rmw_fleetqox_cpp::decode_action_frame(
    rmw_fleetqox_cpp::encode_service_frame(
      rmw_fleetqox_cpp::ServiceFrame{
        "request",
        "/fleetqox/set_bool",
        "std_srvs/srv/SetBool",
        "client-1",
        "service-1",
        1,
        1000000,
        5000000,
        {0x01}}));

  const bool ok = roundtrip_ok && not_expired && expired && rejects_service_schema;

  std::cout << "{\"schema_version\":\"fleetrmw.rmw_action_frame_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"action_name\":\"/fleetqox/navigate_to_pose\",";
  std::cout << "\"type_name\":\"nav2_msgs/action/NavigateToPose\",";
  std::cout << "\"role_count\":" << decoded_roles.size() << ",";
  std::cout << "\"roles\":[";
  for (size_t i = 0; i < decoded_roles.size(); ++i) {
    if (i > 0) {
      std::cout << ",";
    }
    std::cout << "\"" << json_escape(decoded_roles[i]) << "\"";
  }
  std::cout << "],";
  std::cout << "\"lifespan_ns\":5000000,";
  std::cout << "\"not_expired\":" << (not_expired ? "true" : "false") << ",";
  std::cout << "\"expired\":" << (expired ? "true" : "false") << ",";
  std::cout << "\"rejects_service_schema\":" << (rejects_service_schema ? "true" : "false") << "}"
            << std::endl;

  return ok ? 0 : 1;
}
