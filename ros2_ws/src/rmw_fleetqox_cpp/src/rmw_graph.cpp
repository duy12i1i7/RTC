#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include "rcutils/allocator.h"
#include "rcutils/strdup.h"
#include "rcutils/types/string_array.h"
#include "rmw/error_handling.h"
#include "rmw/get_node_info_and_types.h"
#include "rmw/get_service_names_and_types.h"
#include "rmw/get_topic_endpoint_info.h"
#include "rmw/names_and_types.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/topic_endpoint_info_array.h"

namespace
{

constexpr const char * kIdentifier = "rmw_fleetqox_cpp";

struct NodeRecord
{
  std::string name;
  std::string namespace_;
  std::size_t count = 0;
};

struct TopicRecord
{
  std::string name;
  std::set<std::string> types;
  std::map<std::string, std::size_t> type_counts;
  std::size_t publisher_count = 0;
  std::size_t subscription_count = 0;
};

struct ServiceRecord
{
  std::string name;
  std::set<std::string> types;
  std::map<std::string, std::size_t> type_counts;
  std::size_t service_count = 0;
  std::size_t client_count = 0;
};

using RemoteGraphKey = std::tuple<
  std::string,
  std::string,
  std::string,
  std::string,
  std::string,
  std::string>;
using SteadyClock = std::chrono::steady_clock;

struct RemoteGraphEndpoint
{
  bool publisher = false;
  std::string node_name;
  std::string node_namespace;
  std::string topic_name;
  std::string type_name;
  std::string endpoint_id;
  std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> endpoint_gid{};
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  SteadyClock::time_point expires_at;
};

struct LocalGraphEndpoint
{
  bool publisher = false;
  std::string node_name;
  std::string node_namespace;
  std::string topic_name;
  std::string type_name;
  std::string endpoint_id;
  std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> endpoint_gid{};
  rmw_qos_profile_t qos = rmw_qos_profile_default;
};

struct TopicEndpointSnapshot
{
  bool publisher = false;
  std::string node_name;
  std::string node_namespace;
  std::string topic_name;
  std::string type_name;
  std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> endpoint_gid{};
  rmw_qos_profile_t qos = rmw_qos_profile_default;
};

struct LocalServiceGraphEndpoint
{
  bool service = false;
  std::string node_name;
  std::string node_namespace;
  std::string service_name;
  std::string type_name;
  std::string endpoint_id;
};

struct RemoteServiceGraphEndpoint
{
  bool service = false;
  std::string node_name;
  std::string node_namespace;
  std::string service_name;
  std::string type_name;
  std::string endpoint_id;
  SteadyClock::time_point expires_at;
};

std::mutex g_graph_mutex;
std::map<std::pair<std::string, std::string>, NodeRecord> g_nodes;
std::map<std::string, TopicRecord> g_topics;
std::map<std::string, ServiceRecord> g_services;
std::map<std::string, LocalGraphEndpoint> g_local_graph_endpoints;
std::map<RemoteGraphKey, RemoteGraphEndpoint> g_remote_graph_endpoints;
std::map<std::string, LocalServiceGraphEndpoint> g_local_service_endpoints;
std::map<RemoteGraphKey, RemoteServiceGraphEndpoint> g_remote_service_endpoints;

bool identifier_matches(const char * identifier)
{
  return identifier != nullptr && std::strcmp(identifier, kIdentifier) == 0;
}

bool node_is_valid(const rmw_node_t * node)
{
  return node != nullptr && identifier_matches(node->implementation_identifier);
}

bool topic_is_valid(const char * topic_name)
{
  return topic_name != nullptr && topic_name[0] == '/';
}

rmw_ret_t require_graph_query_args(const rmw_node_t * node)
{
  if (!node_is_valid(node)) {
    RMW_SET_ERROR_MSG("node is not a valid rmw_fleetqox_cpp node");
    return node == nullptr ? RMW_RET_INVALID_ARGUMENT : RMW_RET_INCORRECT_RMW_IMPLEMENTATION;
  }
  return RMW_RET_OK;
}

std::chrono::milliseconds lease_duration(std::uint64_t lease_ms)
{
  return std::chrono::milliseconds(lease_ms == 0 ? 5000 : lease_ms);
}

std::string local_endpoint_key(bool publisher, const std::string & endpoint_id)
{
  return std::string(publisher ? "publisher:" : "subscription:") + endpoint_id;
}

std::string local_service_endpoint_key(bool service, const std::string & endpoint_id)
{
  return std::string(service ? "service:" : "client:") + endpoint_id;
}

std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> copy_endpoint_gid(
  const std::uint8_t * endpoint_gid,
  size_t endpoint_gid_size)
{
  std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> gid{};
  if (endpoint_gid == nullptr || endpoint_gid_size == 0) {
    return gid;
  }
  const size_t copy_size = std::min(endpoint_gid_size, static_cast<size_t>(RMW_GID_STORAGE_SIZE));
  std::memcpy(gid.data(), endpoint_gid, copy_size);
  return gid;
}

void add_topic_endpoint_locked(const std::string & topic_name, const std::string & type_name, bool publisher)
{
  TopicRecord & record = g_topics[topic_name];
  record.name = topic_name;
  record.types.insert(type_name);
  ++record.type_counts[type_name];
  if (publisher) {
    ++record.publisher_count;
  } else {
    ++record.subscription_count;
  }
}

void remove_topic_endpoint_locked(const std::string & topic_name, const std::string & type_name, bool publisher)
{
  auto found = g_topics.find(topic_name);
  if (found == g_topics.end()) {
    return;
  }
  TopicRecord & record = found->second;
  if (publisher && record.publisher_count > 0) {
    --record.publisher_count;
  } else if (!publisher && record.subscription_count > 0) {
    --record.subscription_count;
  }

  auto type_found = record.type_counts.find(type_name);
  if (type_found != record.type_counts.end()) {
    if (type_found->second > 1) {
      --type_found->second;
    } else {
      record.type_counts.erase(type_found);
      record.types.erase(type_name);
    }
  }

  if (record.publisher_count == 0 && record.subscription_count == 0) {
    g_topics.erase(found);
  }
}

void add_service_endpoint_locked(const std::string & service_name, const std::string & type_name, bool service)
{
  ServiceRecord & record = g_services[service_name];
  record.name = service_name;
  record.types.insert(type_name);
  ++record.type_counts[type_name];
  if (service) {
    ++record.service_count;
  } else {
    ++record.client_count;
  }
}

void remove_service_endpoint_locked(const std::string & service_name, const std::string & type_name, bool service)
{
  auto found = g_services.find(service_name);
  if (found == g_services.end()) {
    return;
  }
  ServiceRecord & record = found->second;
  if (service && record.service_count > 0) {
    --record.service_count;
  } else if (!service && record.client_count > 0) {
    --record.client_count;
  }

  auto type_found = record.type_counts.find(type_name);
  if (type_found != record.type_counts.end()) {
    if (type_found->second > 1) {
      --type_found->second;
    } else {
      record.type_counts.erase(type_found);
      record.types.erase(type_name);
    }
  }

  if (record.service_count == 0 && record.client_count == 0) {
    g_services.erase(found);
  }
}

void remove_local_endpoint_locked(const LocalGraphEndpoint & endpoint)
{
  remove_topic_endpoint_locked(endpoint.topic_name, endpoint.type_name, endpoint.publisher);
}

void remove_local_service_endpoint_locked(const LocalServiceGraphEndpoint & endpoint)
{
  remove_service_endpoint_locked(endpoint.service_name, endpoint.type_name, endpoint.service);
}

void remove_local_endpoint_locked(bool publisher, const char * endpoint_id)
{
  if (endpoint_id == nullptr) {
    return;
  }
  const auto found = g_local_graph_endpoints.find(local_endpoint_key(publisher, endpoint_id));
  if (found == g_local_graph_endpoints.end()) {
    return;
  }
  remove_local_endpoint_locked(found->second);
  g_local_graph_endpoints.erase(found);
}

void remove_local_service_endpoint_locked(bool service, const char * endpoint_id)
{
  if (endpoint_id == nullptr) {
    return;
  }
  const auto found = g_local_service_endpoints.find(local_service_endpoint_key(service, endpoint_id));
  if (found == g_local_service_endpoints.end()) {
    return;
  }
  remove_local_service_endpoint_locked(found->second);
  g_local_service_endpoints.erase(found);
}

void add_topic_endpoint(const char * topic_name, const char * type_name, bool publisher)
{
  if (topic_name == nullptr || type_name == nullptr) {
    return;
  }
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  add_topic_endpoint_locked(topic_name, type_name, publisher);
}

void add_local_endpoint(
  bool publisher,
  const char * node_name,
  const char * node_namespace,
  const char * topic_name,
  const char * type_name,
  const char * endpoint_id,
  const std::uint8_t * endpoint_gid,
  size_t endpoint_gid_size,
  const rmw_qos_profile_t * qos)
{
  if (topic_name == nullptr || type_name == nullptr || endpoint_id == nullptr) {
    return;
  }
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  const std::string key = local_endpoint_key(publisher, endpoint_id);
  auto found = g_local_graph_endpoints.find(key);
  if (found != g_local_graph_endpoints.end()) {
    remove_local_endpoint_locked(found->second);
    g_local_graph_endpoints.erase(found);
  }
  add_topic_endpoint_locked(topic_name, type_name, publisher);
  g_local_graph_endpoints.emplace(
    key,
    LocalGraphEndpoint{
      publisher,
      node_name != nullptr ? node_name : "",
      node_namespace != nullptr ? node_namespace : "",
      topic_name,
      type_name,
      endpoint_id,
      copy_endpoint_gid(endpoint_gid, endpoint_gid_size),
      qos != nullptr ? *qos : rmw_qos_profile_default});
}

void add_local_service_endpoint(
  bool service,
  const char * node_name,
  const char * node_namespace,
  const char * service_name,
  const char * type_name,
  const char * endpoint_id)
{
  if (service_name == nullptr || type_name == nullptr || endpoint_id == nullptr) {
    return;
  }
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  const std::string key = local_service_endpoint_key(service, endpoint_id);
  auto found = g_local_service_endpoints.find(key);
  if (found != g_local_service_endpoints.end()) {
    remove_local_service_endpoint_locked(found->second);
    g_local_service_endpoints.erase(found);
  }
  add_service_endpoint_locked(service_name, type_name, service);
  g_local_service_endpoints.emplace(
    key,
    LocalServiceGraphEndpoint{
      service,
      node_name != nullptr ? node_name : "",
      node_namespace != nullptr ? node_namespace : "",
      service_name,
      type_name,
      endpoint_id});
}

void remove_topic_endpoint(const char * topic_name, const char * type_name, bool publisher)
{
  if (topic_name == nullptr || type_name == nullptr) {
    return;
  }
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  remove_topic_endpoint_locked(topic_name, type_name, publisher);
}

void remove_remote_endpoint_locked(const RemoteGraphEndpoint & endpoint)
{
  remove_topic_endpoint_locked(endpoint.topic_name, endpoint.type_name, endpoint.publisher);
  if (!endpoint.node_name.empty()) {
    auto found = g_nodes.find(std::make_pair(endpoint.node_name, endpoint.node_namespace));
    if (found != g_nodes.end()) {
      if (found->second.count > 1) {
        --found->second.count;
      } else {
        g_nodes.erase(found);
      }
    }
  }
}

void remove_remote_service_endpoint_locked(const RemoteServiceGraphEndpoint & endpoint)
{
  remove_service_endpoint_locked(endpoint.service_name, endpoint.type_name, endpoint.service);
  if (!endpoint.node_name.empty()) {
    auto found = g_nodes.find(std::make_pair(endpoint.node_name, endpoint.node_namespace));
    if (found != g_nodes.end()) {
      if (found->second.count > 1) {
        --found->second.count;
      } else {
        g_nodes.erase(found);
      }
    }
  }
}

void purge_expired_remote_graph_locked(SteadyClock::time_point now)
{
  for (auto it = g_remote_graph_endpoints.begin(); it != g_remote_graph_endpoints.end();) {
    if (it->second.expires_at > now) {
      ++it;
      continue;
    }
    remove_remote_endpoint_locked(it->second);
    it = g_remote_graph_endpoints.erase(it);
  }
  for (auto it = g_remote_service_endpoints.begin(); it != g_remote_service_endpoints.end();) {
    if (it->second.expires_at > now) {
      ++it;
      continue;
    }
    remove_remote_service_endpoint_locked(it->second);
    it = g_remote_service_endpoints.erase(it);
  }
}

std::vector<TopicEndpointSnapshot> endpoint_snapshot(const std::string & topic_name, bool publisher)
{
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  purge_expired_remote_graph_locked(SteadyClock::now());
  std::vector<TopicEndpointSnapshot> endpoints;
  for (const auto & item : g_local_graph_endpoints) {
    const LocalGraphEndpoint & endpoint = item.second;
    if (endpoint.publisher != publisher || endpoint.topic_name != topic_name) {
      continue;
    }
    endpoints.push_back(
      TopicEndpointSnapshot{
        endpoint.publisher,
        endpoint.node_name,
        endpoint.node_namespace,
        endpoint.topic_name,
        endpoint.type_name,
        endpoint.endpoint_gid,
        endpoint.qos});
  }
  for (const auto & item : g_remote_graph_endpoints) {
    const RemoteGraphEndpoint & endpoint = item.second;
    if (endpoint.publisher != publisher || endpoint.topic_name != topic_name) {
      continue;
    }
    endpoints.push_back(
      TopicEndpointSnapshot{
        endpoint.publisher,
        endpoint.node_name,
        endpoint.node_namespace,
        endpoint.topic_name,
        endpoint.type_name,
        endpoint.endpoint_gid,
        endpoint.qos});
  }
  return endpoints;
}

rmw_ret_t fill_string_array(
  rcutils_string_array_t * output,
  const std::vector<std::string> & values,
  rcutils_allocator_t * allocator)
{
  if (output == nullptr || allocator == nullptr || !rcutils_allocator_is_valid(allocator)) {
    RMW_SET_ERROR_MSG("invalid string array output or allocator");
    return RMW_RET_INVALID_ARGUMENT;
  }
  if (output->data != nullptr || output->size != 0) {
    RMW_SET_ERROR_MSG("string array output must be zero initialized");
    return RMW_RET_INVALID_ARGUMENT;
  }
  if (rcutils_string_array_init(output, values.size(), allocator) != RCUTILS_RET_OK) {
    RMW_SET_ERROR_MSG("failed to initialize string array");
    return RMW_RET_BAD_ALLOC;
  }
  for (std::size_t i = 0; i < values.size(); ++i) {
    output->data[i] = rcutils_strdup(values[i].c_str(), *allocator);
    if (output->data[i] == nullptr) {
      const rcutils_ret_t fini_ret = rcutils_string_array_fini(output);
      (void)fini_ret;
      RMW_SET_ERROR_MSG("failed to copy graph string");
      return RMW_RET_BAD_ALLOC;
    }
  }
  return RMW_RET_OK;
}

rmw_ret_t set_topic_endpoint_info(
  rmw_topic_endpoint_info_t * info,
  const TopicEndpointSnapshot & endpoint,
  rcutils_allocator_t * allocator)
{
  rmw_ret_t ret = rmw_topic_endpoint_info_set_node_name(
    info,
    endpoint.node_name.c_str(),
    allocator);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  ret = rmw_topic_endpoint_info_set_node_namespace(
    info,
    endpoint.node_namespace.c_str(),
    allocator);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  ret = rmw_topic_endpoint_info_set_topic_type(
    info,
    endpoint.type_name.c_str(),
    allocator);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  ret = rmw_topic_endpoint_info_set_endpoint_type(
    info,
    endpoint.publisher ? RMW_ENDPOINT_PUBLISHER : RMW_ENDPOINT_SUBSCRIPTION);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  ret = rmw_topic_endpoint_info_set_gid(
    info,
    endpoint.endpoint_gid.data(),
    endpoint.endpoint_gid.size());
  if (ret != RMW_RET_OK) {
    return ret;
  }
  return rmw_topic_endpoint_info_set_qos_profile(info, &endpoint.qos);
}

rmw_ret_t fill_topic_endpoint_info_array(
  rcutils_allocator_t * allocator,
  const std::vector<TopicEndpointSnapshot> & endpoints,
  rmw_topic_endpoint_info_array_t * info_array)
{
  if (allocator == nullptr || !rcutils_allocator_is_valid(allocator) || info_array == nullptr) {
    RMW_SET_ERROR_MSG("invalid allocator or topic endpoint info output");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = rmw_topic_endpoint_info_array_init_with_size(
    info_array,
    endpoints.size(),
    allocator);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  for (std::size_t i = 0; i < endpoints.size(); ++i) {
    ret = set_topic_endpoint_info(&info_array->info_array[i], endpoints[i], allocator);
    if (ret != RMW_RET_OK) {
      const rmw_ret_t fini_ret = rmw_topic_endpoint_info_array_fini(info_array, allocator);
      (void)fini_ret;
      return ret;
    }
  }
  return RMW_RET_OK;
}

rmw_ret_t fill_names_and_types(
  rmw_names_and_types_t * output,
  const std::vector<TopicRecord> & topics,
  rcutils_allocator_t * allocator)
{
  if (output == nullptr || allocator == nullptr || !rcutils_allocator_is_valid(allocator)) {
    RMW_SET_ERROR_MSG("invalid names_and_types output or allocator");
    return RMW_RET_INVALID_ARGUMENT;
  }
  if (output->names.data != nullptr || output->names.size != 0 || output->types != nullptr) {
    RMW_SET_ERROR_MSG("names_and_types output must be zero initialized");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = rmw_names_and_types_init(output, topics.size(), allocator);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  for (std::size_t i = 0; i < topics.size(); ++i) {
    output->names.data[i] = rcutils_strdup(topics[i].name.c_str(), *allocator);
    if (output->names.data[i] == nullptr) {
      const rmw_ret_t fini_ret = rmw_names_and_types_fini(output);
      (void)fini_ret;
      RMW_SET_ERROR_MSG("failed to copy topic name");
      return RMW_RET_BAD_ALLOC;
    }
    const std::size_t type_count = topics[i].types.size();
    if (rcutils_string_array_init(&output->types[i], type_count, allocator) != RCUTILS_RET_OK) {
      const rmw_ret_t fini_ret = rmw_names_and_types_fini(output);
      (void)fini_ret;
      RMW_SET_ERROR_MSG("failed to initialize topic type array");
      return RMW_RET_BAD_ALLOC;
    }
    std::size_t type_index = 0;
    for (const std::string & type : topics[i].types) {
      output->types[i].data[type_index] = rcutils_strdup(type.c_str(), *allocator);
      if (output->types[i].data[type_index] == nullptr) {
        const rmw_ret_t fini_ret = rmw_names_and_types_fini(output);
        (void)fini_ret;
        RMW_SET_ERROR_MSG("failed to copy topic type");
        return RMW_RET_BAD_ALLOC;
      }
      ++type_index;
    }
  }
  return RMW_RET_OK;
}

std::vector<TopicRecord> topic_snapshot()
{
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  purge_expired_remote_graph_locked(SteadyClock::now());
  std::vector<TopicRecord> topics;
  topics.reserve(g_topics.size());
  for (const auto & item : g_topics) {
    topics.push_back(item.second);
  }
  return topics;
}

std::vector<TopicRecord> service_snapshot()
{
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  purge_expired_remote_graph_locked(SteadyClock::now());
  std::vector<TopicRecord> services;
  services.reserve(g_services.size());
  for (const auto & item : g_services) {
    if (item.second.service_count == 0) {
      continue;
    }
    TopicRecord record{};
    record.name = item.second.name;
    record.types = item.second.types;
    services.push_back(record);
  }
  return services;
}

void add_endpoint_topic_record(
  std::map<std::string, TopicRecord> * records,
  const std::string & topic_name,
  const std::string & type_name)
{
  if (records == nullptr) {
    return;
  }
  TopicRecord & record = (*records)[topic_name];
  record.name = topic_name;
  record.types.insert(type_name);
}

void add_endpoint_service_record(
  std::map<std::string, TopicRecord> * records,
  const std::string & service_name,
  const std::string & type_name)
{
  add_endpoint_topic_record(records, service_name, type_name);
}

std::vector<TopicRecord> topic_snapshot_by_node(
  const char * node_name,
  const char * node_namespace,
  bool publisher,
  bool * node_found)
{
  if (node_found != nullptr) {
    *node_found = false;
  }
  if (node_name == nullptr || node_namespace == nullptr) {
    return {};
  }
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  purge_expired_remote_graph_locked(SteadyClock::now());
  const std::string requested_name = node_name;
  const std::string requested_namespace = node_namespace;
  const auto node_key = std::make_pair(requested_name, requested_namespace);
  if (g_nodes.find(node_key) == g_nodes.end()) {
    return {};
  }
  if (node_found != nullptr) {
    *node_found = true;
  }
  std::map<std::string, TopicRecord> records;
  for (const auto & item : g_local_graph_endpoints) {
    const LocalGraphEndpoint & endpoint = item.second;
    if (endpoint.publisher == publisher &&
      endpoint.node_name == requested_name &&
      endpoint.node_namespace == requested_namespace)
    {
      add_endpoint_topic_record(&records, endpoint.topic_name, endpoint.type_name);
    }
  }
  for (const auto & item : g_remote_graph_endpoints) {
    const RemoteGraphEndpoint & endpoint = item.second;
    if (endpoint.publisher == publisher &&
      endpoint.node_name == requested_name &&
      endpoint.node_namespace == requested_namespace)
    {
      add_endpoint_topic_record(&records, endpoint.topic_name, endpoint.type_name);
    }
  }
  std::vector<TopicRecord> topics;
  topics.reserve(records.size());
  for (const auto & item : records) {
    topics.push_back(item.second);
  }
  return topics;
}

std::vector<TopicRecord> service_snapshot_by_node(
  const char * node_name,
  const char * node_namespace,
  bool service,
  bool * node_found)
{
  if (node_found != nullptr) {
    *node_found = false;
  }
  if (node_name == nullptr || node_namespace == nullptr) {
    return {};
  }
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  purge_expired_remote_graph_locked(SteadyClock::now());
  const std::string requested_name = node_name;
  const std::string requested_namespace = node_namespace;
  const auto node_key = std::make_pair(requested_name, requested_namespace);
  if (g_nodes.find(node_key) == g_nodes.end()) {
    return {};
  }
  if (node_found != nullptr) {
    *node_found = true;
  }
  std::map<std::string, TopicRecord> records;
  for (const auto & item : g_local_service_endpoints) {
    const LocalServiceGraphEndpoint & endpoint = item.second;
    if (endpoint.service == service &&
      endpoint.node_name == requested_name &&
      endpoint.node_namespace == requested_namespace)
    {
      add_endpoint_service_record(&records, endpoint.service_name, endpoint.type_name);
    }
  }
  for (const auto & item : g_remote_service_endpoints) {
    const RemoteServiceGraphEndpoint & endpoint = item.second;
    if (endpoint.service == service &&
      endpoint.node_name == requested_name &&
      endpoint.node_namespace == requested_namespace)
    {
      add_endpoint_service_record(&records, endpoint.service_name, endpoint.type_name);
    }
  }
  std::vector<TopicRecord> services;
  services.reserve(records.size());
  for (const auto & item : records) {
    services.push_back(item.second);
  }
  return services;
}

}  // namespace

extern "C"
{

void rmw_fleetqox_cpp_graph_register_node(const char * name, const char * namespace_)
{
  if (name == nullptr || namespace_ == nullptr) {
    return;
  }
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  auto key = std::make_pair(std::string(name), std::string(namespace_));
  NodeRecord & record = g_nodes[key];
  record.name = name;
  record.namespace_ = namespace_;
  ++record.count;
}

void rmw_fleetqox_cpp_graph_unregister_node(const char * name, const char * namespace_)
{
  if (name == nullptr || namespace_ == nullptr) {
    return;
  }
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  auto found = g_nodes.find(std::make_pair(std::string(name), std::string(namespace_)));
  if (found == g_nodes.end()) {
    return;
  }
  if (found->second.count > 1) {
    --found->second.count;
  } else {
    g_nodes.erase(found);
  }
}

void rmw_fleetqox_cpp_graph_register_publisher(const char * topic_name, const char * type_name)
{
  add_topic_endpoint(topic_name, type_name, true);
}

void rmw_fleetqox_cpp_graph_unregister_publisher(const char * topic_name, const char * type_name)
{
  remove_topic_endpoint(topic_name, type_name, true);
}

void rmw_fleetqox_cpp_graph_register_subscription(const char * topic_name, const char * type_name)
{
  add_topic_endpoint(topic_name, type_name, false);
}

void rmw_fleetqox_cpp_graph_unregister_subscription(const char * topic_name, const char * type_name)
{
  remove_topic_endpoint(topic_name, type_name, false);
}

void rmw_fleetqox_cpp_graph_register_publisher_endpoint(
  const char * node_name,
  const char * node_namespace,
  const char * topic_name,
  const char * type_name,
  const char * endpoint_id,
  const std::uint8_t * endpoint_gid,
  size_t endpoint_gid_size,
  const rmw_qos_profile_t * qos)
{
  add_local_endpoint(
    true,
    node_name,
    node_namespace,
    topic_name,
    type_name,
    endpoint_id,
    endpoint_gid,
    endpoint_gid_size,
    qos);
}

void rmw_fleetqox_cpp_graph_unregister_publisher_endpoint(const char * endpoint_id)
{
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  remove_local_endpoint_locked(true, endpoint_id);
}

void rmw_fleetqox_cpp_graph_register_subscription_endpoint(
  const char * node_name,
  const char * node_namespace,
  const char * topic_name,
  const char * type_name,
  const char * endpoint_id,
  const std::uint8_t * endpoint_gid,
  size_t endpoint_gid_size,
  const rmw_qos_profile_t * qos)
{
  add_local_endpoint(
    false,
    node_name,
    node_namespace,
    topic_name,
    type_name,
    endpoint_id,
    endpoint_gid,
    endpoint_gid_size,
    qos);
}

void rmw_fleetqox_cpp_graph_unregister_subscription_endpoint(const char * endpoint_id)
{
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  remove_local_endpoint_locked(false, endpoint_id);
}

void rmw_fleetqox_cpp_graph_register_service_endpoint(
  const char * node_name,
  const char * node_namespace,
  const char * service_name,
  const char * type_name,
  const char * endpoint_id)
{
  add_local_service_endpoint(true, node_name, node_namespace, service_name, type_name, endpoint_id);
}

void rmw_fleetqox_cpp_graph_unregister_service_endpoint(const char * endpoint_id)
{
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  remove_local_service_endpoint_locked(true, endpoint_id);
}

void rmw_fleetqox_cpp_graph_register_client_endpoint(
  const char * node_name,
  const char * node_namespace,
  const char * service_name,
  const char * type_name,
  const char * endpoint_id)
{
  add_local_service_endpoint(false, node_name, node_namespace, service_name, type_name, endpoint_id);
}

void rmw_fleetqox_cpp_graph_unregister_client_endpoint(const char * endpoint_id)
{
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  remove_local_service_endpoint_locked(false, endpoint_id);
}

void rmw_fleetqox_cpp_graph_apply_remote_advertisement_with_info(
  const char * action,
  const char * entity_kind,
  const char * node_name,
  const char * node_namespace,
  const char * topic_name,
  const char * type_name,
  const char * endpoint_id,
  const std::uint8_t * endpoint_gid,
  size_t endpoint_gid_size,
  const rmw_qos_profile_t * qos,
  std::uint64_t lease_ms)
{
  if (action == nullptr || entity_kind == nullptr || topic_name == nullptr || type_name == nullptr ||
    endpoint_id == nullptr)
  {
    return;
  }
  const bool is_add = std::strcmp(action, "add") == 0;
  const bool is_remove = std::strcmp(action, "remove") == 0;
  if (!is_add && !is_remove) {
    return;
  }
  const bool is_publisher = std::strcmp(entity_kind, "publisher") == 0;
  const bool is_subscription = std::strcmp(entity_kind, "subscription") == 0;
  const bool is_service = std::strcmp(entity_kind, "service") == 0;
  const bool is_client = std::strcmp(entity_kind, "client") == 0;
  const bool is_topic_endpoint = is_publisher || is_subscription;
  const bool is_service_endpoint = is_service || is_client;
  if (!is_topic_endpoint && !is_service_endpoint) {
    return;
  }

  std::lock_guard<std::mutex> lock(g_graph_mutex);
  purge_expired_remote_graph_locked(SteadyClock::now());
  const auto key = std::make_tuple(
    std::string(endpoint_id),
    std::string(entity_kind),
    std::string(topic_name),
    std::string(type_name),
    std::string(node_name != nullptr ? node_name : ""),
    std::string(node_namespace != nullptr ? node_namespace : ""));

  if (is_service_endpoint) {
    auto service_found = g_remote_service_endpoints.find(key);
    if (is_remove) {
      if (service_found != g_remote_service_endpoints.end()) {
        remove_remote_service_endpoint_locked(service_found->second);
        g_remote_service_endpoints.erase(service_found);
      }
      return;
    }
    if (service_found != g_remote_service_endpoints.end()) {
      service_found->second.expires_at = SteadyClock::now() + lease_duration(lease_ms);
      return;
    }
    if (node_name != nullptr && node_name[0] != '\0' && node_namespace != nullptr) {
      auto node_key = std::make_pair(std::string(node_name), std::string(node_namespace));
      NodeRecord & node_record = g_nodes[node_key];
      node_record.name = node_name;
      node_record.namespace_ = node_namespace;
      ++node_record.count;
    }
    add_service_endpoint_locked(topic_name, type_name, is_service);
    g_remote_service_endpoints.emplace(
      key,
      RemoteServiceGraphEndpoint{
        is_service,
        node_name != nullptr ? node_name : "",
        node_namespace != nullptr ? node_namespace : "",
        topic_name,
        type_name,
        endpoint_id,
        SteadyClock::now() + lease_duration(lease_ms)});
    return;
  }

  auto found = g_remote_graph_endpoints.find(key);
  if (is_remove) {
    if (found != g_remote_graph_endpoints.end()) {
      remove_remote_endpoint_locked(found->second);
      g_remote_graph_endpoints.erase(found);
    }
    return;
  }

  if (found != g_remote_graph_endpoints.end()) {
    found->second.expires_at = SteadyClock::now() + lease_duration(lease_ms);
    found->second.endpoint_gid = copy_endpoint_gid(endpoint_gid, endpoint_gid_size);
    found->second.qos = qos != nullptr ? *qos : rmw_qos_profile_default;
    return;
  }

  if (node_name != nullptr && node_name[0] != '\0' && node_namespace != nullptr) {
    auto node_key = std::make_pair(std::string(node_name), std::string(node_namespace));
    NodeRecord & node_record = g_nodes[node_key];
    node_record.name = node_name;
    node_record.namespace_ = node_namespace;
    ++node_record.count;
  }
  add_topic_endpoint_locked(topic_name, type_name, is_publisher);
  g_remote_graph_endpoints.emplace(
    key,
    RemoteGraphEndpoint{
      is_publisher,
      node_name != nullptr ? node_name : "",
      node_namespace != nullptr ? node_namespace : "",
      topic_name,
      type_name,
      endpoint_id,
      copy_endpoint_gid(endpoint_gid, endpoint_gid_size),
      qos != nullptr ? *qos : rmw_qos_profile_default,
      SteadyClock::now() + lease_duration(lease_ms)});
}

void rmw_fleetqox_cpp_graph_apply_remote_advertisement(
  const char * action,
  const char * entity_kind,
  const char * node_name,
  const char * node_namespace,
  const char * topic_name,
  const char * type_name,
  const char * endpoint_id,
  std::uint64_t lease_ms)
{
  rmw_fleetqox_cpp_graph_apply_remote_advertisement_with_info(
    action,
    entity_kind,
    node_name,
    node_namespace,
    topic_name,
    type_name,
    endpoint_id,
    nullptr,
    0,
    nullptr,
    lease_ms);
}

rmw_ret_t rmw_get_node_names(
  const rmw_node_t * node,
  rcutils_string_array_t * node_names,
  rcutils_string_array_t * node_namespaces)
{
  rmw_ret_t ret = require_graph_query_args(node);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (node_names == nullptr || node_namespaces == nullptr) {
    RMW_SET_ERROR_MSG("node name arrays must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  std::vector<std::string> names;
  std::vector<std::string> namespaces;
  {
    std::lock_guard<std::mutex> lock(g_graph_mutex);
    purge_expired_remote_graph_locked(SteadyClock::now());
    names.reserve(g_nodes.size());
    namespaces.reserve(g_nodes.size());
    for (const auto & item : g_nodes) {
      names.push_back(item.second.name);
      namespaces.push_back(item.second.namespace_);
    }
  }
  rcutils_allocator_t allocator = node->context->options.allocator;
  ret = fill_string_array(node_names, names, &allocator);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  ret = fill_string_array(node_namespaces, namespaces, &allocator);
  if (ret != RMW_RET_OK) {
    const rcutils_ret_t fini_ret = rcutils_string_array_fini(node_names);
    (void)fini_ret;
    return ret;
  }
  return RMW_RET_OK;
}

rmw_ret_t rmw_get_node_names_with_enclaves(
  const rmw_node_t * node,
  rcutils_string_array_t * node_names,
  rcutils_string_array_t * node_namespaces,
  rcutils_string_array_t * enclaves)
{
  rmw_ret_t ret = rmw_get_node_names(node, node_names, node_namespaces);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  std::vector<std::string> enclave_values(node_names->size, "");
  rcutils_allocator_t allocator = node->context->options.allocator;
  ret = fill_string_array(enclaves, enclave_values, &allocator);
  if (ret != RMW_RET_OK) {
    const rcutils_ret_t names_fini_ret = rcutils_string_array_fini(node_names);
    const rcutils_ret_t namespaces_fini_ret = rcutils_string_array_fini(node_namespaces);
    (void)names_fini_ret;
    (void)namespaces_fini_ret;
    return ret;
  }
  return RMW_RET_OK;
}

rmw_ret_t rmw_get_topic_names_and_types(
  const rmw_node_t * node,
  rcutils_allocator_t * allocator,
  bool no_demangle,
  rmw_names_and_types_t * topic_names_and_types)
{
  (void)no_demangle;
  rmw_ret_t ret = require_graph_query_args(node);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  return fill_names_and_types(topic_names_and_types, topic_snapshot(), allocator);
}

rmw_ret_t rmw_get_service_names_and_types(
  const rmw_node_t * node,
  rcutils_allocator_t * allocator,
  rmw_names_and_types_t * service_names_and_types)
{
  rmw_ret_t ret = require_graph_query_args(node);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  return fill_names_and_types(service_names_and_types, service_snapshot(), allocator);
}

rmw_ret_t rmw_get_publisher_names_and_types_by_node(
  const rmw_node_t * node,
  rcutils_allocator_t * allocator,
  const char * node_name,
  const char * node_namespace,
  bool no_demangle,
  rmw_names_and_types_t * topic_names_and_types)
{
  (void)no_demangle;
  rmw_ret_t ret = require_graph_query_args(node);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (node_name == nullptr || node_namespace == nullptr) {
    RMW_SET_ERROR_MSG("node_name and node_namespace must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  bool node_found = false;
  std::vector<TopicRecord> topics =
    topic_snapshot_by_node(node_name, node_namespace, true, &node_found);
  if (!node_found) {
    RMW_SET_ERROR_MSG("node name not found in rmw_fleetqox_cpp graph");
    return RMW_RET_NODE_NAME_NON_EXISTENT;
  }
  return fill_names_and_types(topic_names_and_types, topics, allocator);
}

rmw_ret_t rmw_get_subscriber_names_and_types_by_node(
  const rmw_node_t * node,
  rcutils_allocator_t * allocator,
  const char * node_name,
  const char * node_namespace,
  bool no_demangle,
  rmw_names_and_types_t * topic_names_and_types)
{
  (void)no_demangle;
  rmw_ret_t ret = require_graph_query_args(node);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (node_name == nullptr || node_namespace == nullptr) {
    RMW_SET_ERROR_MSG("node_name and node_namespace must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  bool node_found = false;
  std::vector<TopicRecord> topics =
    topic_snapshot_by_node(node_name, node_namespace, false, &node_found);
  if (!node_found) {
    RMW_SET_ERROR_MSG("node name not found in rmw_fleetqox_cpp graph");
    return RMW_RET_NODE_NAME_NON_EXISTENT;
  }
  return fill_names_and_types(topic_names_and_types, topics, allocator);
}

rmw_ret_t rmw_get_service_names_and_types_by_node(
  const rmw_node_t * node,
  rcutils_allocator_t * allocator,
  const char * node_name,
  const char * node_namespace,
  rmw_names_and_types_t * service_names_and_types)
{
  rmw_ret_t ret = require_graph_query_args(node);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (node_name == nullptr || node_namespace == nullptr) {
    RMW_SET_ERROR_MSG("node_name and node_namespace must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  bool node_found = false;
  std::vector<TopicRecord> services =
    service_snapshot_by_node(node_name, node_namespace, true, &node_found);
  if (!node_found) {
    RMW_SET_ERROR_MSG("node name not found in rmw_fleetqox_cpp graph");
    return RMW_RET_NODE_NAME_NON_EXISTENT;
  }
  return fill_names_and_types(service_names_and_types, services, allocator);
}

rmw_ret_t rmw_get_client_names_and_types_by_node(
  const rmw_node_t * node,
  rcutils_allocator_t * allocator,
  const char * node_name,
  const char * node_namespace,
  rmw_names_and_types_t * service_names_and_types)
{
  rmw_ret_t ret = require_graph_query_args(node);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (node_name == nullptr || node_namespace == nullptr) {
    RMW_SET_ERROR_MSG("node_name and node_namespace must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  bool node_found = false;
  std::vector<TopicRecord> clients =
    service_snapshot_by_node(node_name, node_namespace, false, &node_found);
  if (!node_found) {
    RMW_SET_ERROR_MSG("node name not found in rmw_fleetqox_cpp graph");
    return RMW_RET_NODE_NAME_NON_EXISTENT;
  }
  return fill_names_and_types(service_names_and_types, clients, allocator);
}

rmw_ret_t rmw_count_publishers(
  const rmw_node_t * node,
  const char * topic_name,
  size_t * count)
{
  rmw_ret_t ret = require_graph_query_args(node);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (!topic_is_valid(topic_name) || count == nullptr) {
    RMW_SET_ERROR_MSG("topic_name and count must be valid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  purge_expired_remote_graph_locked(SteadyClock::now());
  const auto found = g_topics.find(topic_name);
  *count = found == g_topics.end() ? 0 : found->second.publisher_count;
  return RMW_RET_OK;
}

rmw_ret_t rmw_count_subscribers(
  const rmw_node_t * node,
  const char * topic_name,
  size_t * count)
{
  rmw_ret_t ret = require_graph_query_args(node);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (!topic_is_valid(topic_name) || count == nullptr) {
    RMW_SET_ERROR_MSG("topic_name and count must be valid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  purge_expired_remote_graph_locked(SteadyClock::now());
  const auto found = g_topics.find(topic_name);
  *count = found == g_topics.end() ? 0 : found->second.subscription_count;
  return RMW_RET_OK;
}

rmw_ret_t rmw_count_services(
  const rmw_node_t * node,
  const char * service_name,
  size_t * count)
{
  rmw_ret_t ret = require_graph_query_args(node);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (!topic_is_valid(service_name) || count == nullptr) {
    RMW_SET_ERROR_MSG("service_name and count must be valid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  purge_expired_remote_graph_locked(SteadyClock::now());
  const auto found = g_services.find(service_name);
  *count = found == g_services.end() ? 0 : found->second.service_count;
  return RMW_RET_OK;
}

rmw_ret_t rmw_count_clients(
  const rmw_node_t * node,
  const char * service_name,
  size_t * count)
{
  rmw_ret_t ret = require_graph_query_args(node);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (!topic_is_valid(service_name) || count == nullptr) {
    RMW_SET_ERROR_MSG("service_name and count must be valid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  purge_expired_remote_graph_locked(SteadyClock::now());
  const auto found = g_services.find(service_name);
  *count = found == g_services.end() ? 0 : found->second.client_count;
  return RMW_RET_OK;
}

size_t rmw_fleetqox_cpp_graph_service_count(const char * service_name)
{
  if (!topic_is_valid(service_name)) {
    return 0;
  }
  std::lock_guard<std::mutex> lock(g_graph_mutex);
  purge_expired_remote_graph_locked(SteadyClock::now());
  const auto found = g_services.find(service_name);
  return found == g_services.end() ? 0 : found->second.service_count;
}

rmw_ret_t rmw_get_publishers_info_by_topic(
  const rmw_node_t * node,
  rcutils_allocator_t * allocator,
  const char * topic_name,
  bool no_mangle,
  rmw_topic_endpoint_info_array_t * publishers_info)
{
  (void)no_mangle;
  rmw_ret_t ret = require_graph_query_args(node);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (topic_name == nullptr) {
    RMW_SET_ERROR_MSG("topic_name must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return fill_topic_endpoint_info_array(
    allocator,
    endpoint_snapshot(topic_name, true),
    publishers_info);
}

rmw_ret_t rmw_get_subscriptions_info_by_topic(
  const rmw_node_t * node,
  rcutils_allocator_t * allocator,
  const char * topic_name,
  bool no_mangle,
  rmw_topic_endpoint_info_array_t * subscriptions_info)
{
  (void)no_mangle;
  rmw_ret_t ret = require_graph_query_args(node);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (topic_name == nullptr) {
    RMW_SET_ERROR_MSG("topic_name must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return fill_topic_endpoint_info_array(
    allocator,
    endpoint_snapshot(topic_name, false),
    subscriptions_info);
}

}  // extern "C"
