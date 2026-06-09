#include <chrono>
#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include "rcutils/allocator.h"
#include "rcutils/types/string_array.h"
#include "rmw/get_topic_names_and_types.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/names_and_types.h"
#include "rmw/rmw.h"

extern "C" std::uint64_t rmw_fleetqox_cpp_socket_frames_received();
extern "C" const char * rmw_fleetqox_cpp_socket_bound_endpoint();
extern "C" size_t rmw_fleetqox_cpp_socket_peer_count();

namespace
{

struct ProbeConfig
{
  std::string topic{"/fleetqox/multicontainer_router_probe"};
  size_t expected_publishers{1};
  size_t expected_subscribers{1};
  int timeout_ms{6000};
};

struct GraphSnapshot
{
  bool topic_found{false};
  size_t topic_count{0};
  size_t node_count{0};
  size_t publisher_count{0};
  size_t subscriber_count{0};
  std::vector<std::string> topic_types;
};

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

ProbeConfig parse_args(int argc, char ** argv)
{
  ProbeConfig config;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--topic" && i + 1 < argc) {
      config.topic = argv[++i];
    } else if (arg == "--expected-publishers" && i + 1 < argc) {
      config.expected_publishers = static_cast<size_t>(std::stoul(argv[++i]));
    } else if (arg == "--expected-subscribers" && i + 1 < argc) {
      config.expected_subscribers = static_cast<size_t>(std::stoul(argv[++i]));
    } else if (arg == "--timeout-ms" && i + 1 < argc) {
      config.timeout_ms = std::stoi(argv[++i]);
    }
  }
  return config;
}

void cleanup_context(rmw_context_t * context, rmw_init_options_t * options)
{
  const rmw_ret_t shutdown_ret = rmw_shutdown(context);
  const rmw_ret_t context_fini_ret = rmw_context_fini(context);
  const rmw_ret_t options_fini_ret = rmw_init_options_fini(options);
  (void)shutdown_ret;
  (void)context_fini_ret;
  (void)options_fini_ret;
}

bool init_context(
  rcutils_allocator_t allocator,
  rmw_init_options_t * options,
  rmw_context_t * context)
{
  *options = rmw_get_zero_initialized_init_options();
  if (rmw_init_options_init(options, allocator) != RMW_RET_OK) {
    return false;
  }
  options->instance_id = 45;
  *context = rmw_get_zero_initialized_context();
  if (rmw_init(options, context) != RMW_RET_OK) {
    const rmw_ret_t fini_ret = rmw_init_options_fini(options);
    (void)fini_ret;
    return false;
  }
  return true;
}

GraphSnapshot snapshot_graph(
  const rmw_node_t * node,
  rcutils_allocator_t * allocator,
  const std::string & topic)
{
  GraphSnapshot snapshot;

  rmw_names_and_types_t names_and_types = rmw_get_zero_initialized_names_and_types();
  if (rmw_get_topic_names_and_types(node, allocator, false, &names_and_types) == RMW_RET_OK) {
    snapshot.topic_count = names_and_types.names.size;
    for (size_t i = 0; i < names_and_types.names.size; ++i) {
      const char * observed_name = names_and_types.names.data[i];
      if (observed_name != nullptr && topic == observed_name) {
        snapshot.topic_found = true;
        const rcutils_string_array_t & types = names_and_types.types[i];
        for (size_t type_index = 0; type_index < types.size; ++type_index) {
          if (types.data[type_index] != nullptr) {
            snapshot.topic_types.emplace_back(types.data[type_index]);
          }
        }
      }
    }
  }
  const rmw_ret_t topics_fini_ret = rmw_names_and_types_fini(&names_and_types);
  (void)topics_fini_ret;

  rcutils_string_array_t node_names = rcutils_get_zero_initialized_string_array();
  rcutils_string_array_t node_namespaces = rcutils_get_zero_initialized_string_array();
  if (rmw_get_node_names(node, &node_names, &node_namespaces) == RMW_RET_OK) {
    snapshot.node_count = node_names.size;
  }
  const rcutils_ret_t names_fini_ret = rcutils_string_array_fini(&node_names);
  const rcutils_ret_t namespaces_fini_ret = rcutils_string_array_fini(&node_namespaces);
  (void)names_fini_ret;
  (void)namespaces_fini_ret;

  const rmw_ret_t publisher_ret =
    rmw_count_publishers(node, topic.c_str(), &snapshot.publisher_count);
  const rmw_ret_t subscriber_ret =
    rmw_count_subscribers(node, topic.c_str(), &snapshot.subscriber_count);
  if (publisher_ret != RMW_RET_OK) {
    snapshot.publisher_count = 0;
  }
  if (subscriber_ret != RMW_RET_OK) {
    snapshot.subscriber_count = 0;
  }
  return snapshot;
}

void print_json_result(
  const ProbeConfig & config,
  const std::string & status,
  const std::string & endpoint,
  size_t peer_count,
  std::uint64_t socket_frames_received,
  const GraphSnapshot & snapshot)
{
  std::cout << "{\"schema_version\":\"fleetrmw.rmw_remote_graph_probe.v1\",";
  std::cout << "\"status\":\"" << status << "\",";
  std::cout << "\"topic\":\"" << json_escape(config.topic) << "\",";
  std::cout << "\"endpoint\":\"" << json_escape(endpoint) << "\",";
  std::cout << "\"peer_count\":" << peer_count << ",";
  std::cout << "\"socket_frames_received\":" << socket_frames_received << ",";
  std::cout << "\"topic_found\":" << (snapshot.topic_found ? "true" : "false") << ",";
  std::cout << "\"topic_count\":" << snapshot.topic_count << ",";
  std::cout << "\"node_count\":" << snapshot.node_count << ",";
  std::cout << "\"expected_publishers\":" << config.expected_publishers << ",";
  std::cout << "\"expected_subscribers\":" << config.expected_subscribers << ",";
  std::cout << "\"publisher_count\":" << snapshot.publisher_count << ",";
  std::cout << "\"subscriber_count\":" << snapshot.subscriber_count << ",";
  std::cout << "\"types\":[";
  for (size_t i = 0; i < snapshot.topic_types.size(); ++i) {
    if (i > 0) {
      std::cout << ",";
    }
    std::cout << "\"" << json_escape(snapshot.topic_types[i]) << "\"";
  }
  std::cout << "]}" << std::endl;
}

}  // namespace

int main(int argc, char ** argv)
{
  const ProbeConfig config = parse_args(argc, argv);
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rmw_init_options_t options{};
  rmw_context_t context{};
  if (!init_context(allocator, &options, &context)) {
    std::cout << "{\"status\":\"init_failed\"}" << std::endl;
    return 1;
  }

  rmw_node_t * node = rmw_create_node(&context, "fleetqox_remote_graph_probe", "/fleetqox");
  if (node == nullptr) {
    cleanup_context(&context, &options);
    std::cout << "{\"status\":\"create_node_failed\"}" << std::endl;
    return 1;
  }

  const std::string endpoint = rmw_fleetqox_cpp_socket_bound_endpoint();
  const size_t peer_count = rmw_fleetqox_cpp_socket_peer_count();
  const std::uint64_t received_before = rmw_fleetqox_cpp_socket_frames_received();
  GraphSnapshot snapshot;
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(config.timeout_ms);
  while (std::chrono::steady_clock::now() < deadline) {
    snapshot = snapshot_graph(node, &allocator, config.topic);
    if (snapshot.topic_found &&
      snapshot.publisher_count >= config.expected_publishers &&
      snapshot.subscriber_count >= config.expected_subscribers)
    {
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  const std::uint64_t received_delta =
    rmw_fleetqox_cpp_socket_frames_received() - received_before;
  const bool ok = snapshot.topic_found &&
                  snapshot.publisher_count >= config.expected_publishers &&
                  snapshot.subscriber_count >= config.expected_subscribers &&
                  received_delta >= config.expected_publishers + config.expected_subscribers;

  print_json_result(
    config,
    ok ? "ok" : "failed",
    endpoint,
    peer_count,
    received_delta,
    snapshot);

  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  (void)destroy_node_ret;
  cleanup_context(&context, &options);
  return ok ? 0 : 1;
}
