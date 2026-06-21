#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <deque>
#include <limits>
#include <map>
#include <mutex>
#include <new>
#include <string>
#include <thread>
#include <vector>

#include "rmw_fleetqox_cpp/data_frame.hpp"

#include "rcutils/allocator.h"
#include "rcutils/strdup.h"
#include "rosidl_typesupport_c/identifier.h"
#include "rosidl_typesupport_c/message_type_support_dispatch.h"
#include "rosidl_typesupport_c/service_type_support_dispatch.h"
#include "rosidl_typesupport_cpp/identifier.hpp"
#include "rosidl_typesupport_cpp/message_type_support_dispatch.hpp"
#include "rosidl_typesupport_cpp/service_type_support_dispatch.hpp"
#include "rosidl_typesupport_introspection_c/identifier.h"
#include "rosidl_typesupport_introspection_c/message_introspection.h"
#include "rosidl_typesupport_introspection_c/service_introspection.h"
#include "rosidl_typesupport_introspection_cpp/identifier.hpp"
#include "rosidl_typesupport_introspection_cpp/message_introspection.hpp"
#include "rosidl_typesupport_introspection_cpp/service_introspection.hpp"
#include "rmw/allocators.h"
#include "rmw/dynamic_message_type_support.h"
#include "rmw/error_handling.h"
#include "rmw/event.h"
#include "rmw/features.h"
#include "rmw/get_network_flow_endpoints.h"
#include "rmw/get_node_info_and_types.h"
#include "rmw/get_service_names_and_types.h"
#include "rmw/names_and_types.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"

extern "C" bool rmw_fleetqox_cpp_publisher_gid(const rmw_publisher_t * publisher, rmw_gid_t * gid);
extern "C" const char * rmw_fleetqox_cpp_socket_bound_endpoint();
extern "C" const char * rmw_fleetqox_cpp_transport_mode();
extern "C" rmw_ret_t rmw_fleetqox_cpp_send_graph_advertisement(
  const char * action,
  const char * entity_kind,
  const char * node_name,
  const char * node_namespace,
  const char * topic_name,
  const char * type_name,
  const char * endpoint_id,
  const rmw_qos_profile_t * qos);
extern "C" rmw_ret_t rmw_fleetqox_cpp_send_encoded_frame(const char * encoded_frame, size_t size);
extern "C" bool rmw_fleetqox_cpp_serialize_introspection_message(
  const rosidl_typesupport_introspection_c__MessageMembers * members,
  const void * ros_message,
  std::vector<std::uint8_t> * payload);
extern "C" bool rmw_fleetqox_cpp_deserialize_introspection_message(
  const rosidl_typesupport_introspection_c__MessageMembers * members,
  const std::vector<std::uint8_t> * payload,
  void * ros_message);
extern "C" bool rmw_fleetqox_cpp_serialize_introspection_cpp_message(
  const rosidl_typesupport_introspection_cpp::MessageMembers * members,
  const void * ros_message,
  std::vector<std::uint8_t> * payload);
extern "C" bool rmw_fleetqox_cpp_max_serialized_size_introspection_message(
  const rosidl_typesupport_introspection_c__MessageMembers * members,
  size_t * size);
extern "C" bool rmw_fleetqox_cpp_max_serialized_size_introspection_cpp_message(
  const rosidl_typesupport_introspection_cpp::MessageMembers * members,
  size_t * size);
extern "C" rmw_ret_t rmw_fleetqox_cpp_borrow_publisher_loan(
  const rmw_publisher_t * publisher,
  const rosidl_message_type_support_t * type_support,
  void ** ros_message);
extern "C" rmw_ret_t rmw_fleetqox_cpp_release_publisher_loan(
  const rmw_publisher_t * publisher,
  void * ros_message);
extern "C" rmw_ret_t rmw_fleetqox_cpp_borrow_subscription_loan(
  const rmw_subscription_t * subscription,
  void ** ros_message);
extern "C" rmw_ret_t rmw_fleetqox_cpp_release_subscription_loan(
  const rmw_subscription_t * subscription,
  void * ros_message);
extern "C" bool rmw_fleetqox_cpp_deserialize_introspection_cpp_message(
  const rosidl_typesupport_introspection_cpp::MessageMembers * members,
  const std::vector<std::uint8_t> * payload,
  void * ros_message);
extern "C" void rmw_fleetqox_cpp_graph_register_service_endpoint(
  const char * node_name,
  const char * node_namespace,
  const char * service_name,
  const char * type_name,
  const char * endpoint_id);
extern "C" void rmw_fleetqox_cpp_graph_unregister_service_endpoint(const char * endpoint_id);
extern "C" void rmw_fleetqox_cpp_graph_register_client_endpoint(
  const char * node_name,
  const char * node_namespace,
  const char * service_name,
  const char * type_name,
  const char * endpoint_id);
extern "C" void rmw_fleetqox_cpp_graph_unregister_client_endpoint(const char * endpoint_id);
extern "C" size_t rmw_fleetqox_cpp_graph_service_count(const char * service_name);

namespace
{

constexpr const char * kIdentifier = "rmw_fleetqox_cpp";

struct FleetQoxServiceData
{
  rcutils_allocator_t allocator;
  char * service_name;
  rmw_qos_profile_t qos;
  bool is_service;
  std::string type_name;
  std::string node_name;
  std::string node_namespace;
  std::string endpoint_id;
  std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> endpoint_gid;
  const rosidl_typesupport_introspection_c__ServiceMembers * service_members;
  const rosidl_typesupport_introspection_c__MessageMembers * request_members;
  const rosidl_typesupport_introspection_c__MessageMembers * response_members;
  const rosidl_typesupport_introspection_cpp::ServiceMembers * cpp_service_members;
  const rosidl_typesupport_introspection_cpp::MessageMembers * cpp_request_members;
  const rosidl_typesupport_introspection_cpp::MessageMembers * cpp_response_members;
  rmw_event_callback_t on_new_request_callback;
  const void * on_new_request_user_data;
  rmw_event_callback_t on_new_response_callback;
  const void * on_new_response_user_data;
  std::int64_t next_sequence_id;
  std::deque<rmw_fleetqox_cpp::ServiceFrame> request_queue;
  std::deque<rmw_fleetqox_cpp::ServiceFrame> response_queue;
  std::map<std::string, std::string> pending_response_clients;
};

std::mutex g_service_graph_mutex;
std::vector<FleetQoxServiceData *> g_service_graph_endpoints;
std::mutex g_service_bus_mutex;
std::vector<FleetQoxServiceData *> g_service_bus_endpoints;
std::vector<rmw_service_t *> g_service_handles;
std::vector<rmw_client_t *> g_client_handles;
std::atomic<bool> g_service_graph_renewal_started{false};
std::atomic<std::uint64_t> g_next_service_endpoint_id{1};
std::atomic<std::uint64_t> g_next_client_endpoint_id{1};
std::atomic<std::uint64_t> g_service_expired_frames_dropped{0};

bool identifier_matches(const char * identifier)
{
  return identifier != nullptr && std::strcmp(identifier, kIdentifier) == 0;
}

bool trace_service_enabled()
{
  const char * value = std::getenv("FLEETQOX_RMW_TRACE_SERVICE");
  return value != nullptr && value[0] != '\0' && std::strcmp(value, "0") != 0;
}

void trace_service_event(
  const char * event,
  const FleetQoxServiceData * data,
  const rmw_fleetqox_cpp::ServiceFrame * frame = nullptr,
  size_t queue_size = 0)
{
  if (!trace_service_enabled()) {
    return;
  }
  std::fprintf(
    stderr,
    "fleetqox service event=%s service=%s endpoint=%s is_service=%s",
    event == nullptr ? "unknown" : event,
    data != nullptr && data->service_name != nullptr ? data->service_name : "",
    data != nullptr ? data->endpoint_id.c_str() : "",
    data != nullptr && data->is_service ? "true" : "false");
  if (frame != nullptr) {
    std::fprintf(
      stderr,
      " role=%s client=%s service_endpoint=%s seq=%ld payload=%zu queue=%zu",
      frame->role.c_str(),
      frame->client_endpoint_id.c_str(),
      frame->service_endpoint_id.c_str(),
      static_cast<long>(frame->sequence_id),
      frame->serialized_payload.size(),
      queue_size);
  }
  std::fprintf(stderr, "\n");
}

rmw_ret_t require_identifier(const char * identifier, const char * entity_name)
{
  if (!identifier_matches(identifier)) {
    RMW_SET_ERROR_MSG(entity_name);
    return RMW_RET_INCORRECT_RMW_IMPLEMENTATION;
  }
  return RMW_RET_OK;
}

rmw_ret_t unsupported(const char * message)
{
  RMW_SET_ERROR_MSG(message);
  return RMW_RET_UNSUPPORTED;
}

rmw_ret_t validate_node(const rmw_node_t * node)
{
  if (node == nullptr) {
    RMW_SET_ERROR_MSG("node is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return require_identifier(node->implementation_identifier, "node is not from rmw_fleetqox_cpp");
}

rmw_ret_t validate_publisher(const rmw_publisher_t * publisher)
{
  if (publisher == nullptr) {
    RMW_SET_ERROR_MSG("publisher is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return require_identifier(
    publisher->implementation_identifier,
    "publisher is not from rmw_fleetqox_cpp");
}

rmw_ret_t validate_subscription(const rmw_subscription_t * subscription)
{
  if (subscription == nullptr) {
    RMW_SET_ERROR_MSG("subscription is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return require_identifier(
    subscription->implementation_identifier,
    "subscription is not from rmw_fleetqox_cpp");
}

rmw_ret_t validate_client(const rmw_client_t * client)
{
  if (client == nullptr) {
    RMW_SET_ERROR_MSG("client is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return require_identifier(client->implementation_identifier, "client is not from rmw_fleetqox_cpp");
}

rmw_ret_t validate_service(const rmw_service_t * service)
{
  if (service == nullptr) {
    RMW_SET_ERROR_MSG("service is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return require_identifier(service->implementation_identifier, "service is not from rmw_fleetqox_cpp");
}

FleetQoxServiceData * service_data(const rmw_service_t * service)
{
  return service == nullptr ? nullptr : static_cast<FleetQoxServiceData *>(service->data);
}

FleetQoxServiceData * client_data(const rmw_client_t * client)
{
  return client == nullptr ? nullptr : static_cast<FleetQoxServiceData *>(client->data);
}

std::uint64_t fnv1a64(const std::string & text, std::uint64_t seed)
{
  std::uint64_t hash = seed;
  for (const unsigned char c : text) {
    hash ^= static_cast<std::uint64_t>(c);
    hash *= 1099511628211ULL;
  }
  return hash;
}

std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> endpoint_gid_from_id(const std::string & endpoint_id)
{
  std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> gid{};
  size_t offset = 0;
  std::uint64_t block = 0;
  while (offset < gid.size()) {
    const std::uint64_t value = fnv1a64(
      endpoint_id + "#" + std::to_string(block),
      1469598103934665603ULL + block);
    for (int byte = 0; byte < 8 && offset < gid.size(); ++byte) {
      gid[offset++] = static_cast<std::uint8_t>((value >> (byte * 8)) & 0xFFu);
    }
    ++block;
  }
  return gid;
}

std::int64_t monotonic_timestamp_ns()
{
  const auto now = std::chrono::steady_clock::now().time_since_epoch();
  return std::chrono::duration_cast<std::chrono::nanoseconds>(now).count();
}

std::int64_t qos_duration_ns(const rmw_time_t & duration)
{
  if (duration.sec == 0 && duration.nsec == 0) {
    return 0;
  }
  constexpr std::uint64_t kNanosecondsPerSecond = 1000000000ull;
  if (duration.sec > static_cast<std::uint64_t>(
      std::numeric_limits<std::int64_t>::max() / static_cast<std::int64_t>(kNanosecondsPerSecond)))
  {
    return std::numeric_limits<std::int64_t>::max();
  }
  const auto sec_ns = static_cast<std::int64_t>(duration.sec * kNanosecondsPerSecond);
  const auto nsec = static_cast<std::int64_t>(duration.nsec);
  if (std::numeric_limits<std::int64_t>::max() - sec_ns < nsec) {
    return std::numeric_limits<std::int64_t>::max();
  }
  return sec_ns + nsec;
}

bool service_frame_exceeds_lifespan(const rmw_fleetqox_cpp::ServiceFrame & frame)
{
  return rmw_fleetqox_cpp::service_frame_expired(frame, monotonic_timestamp_ns());
}

bool drop_if_expired_service_frame(const rmw_fleetqox_cpp::ServiceFrame & frame)
{
  if (!service_frame_exceeds_lifespan(frame)) {
    return false;
  }
  g_service_expired_frames_dropped.fetch_add(1);
  return true;
}

std::string request_key(const std::uint8_t * writer_guid, std::int64_t sequence_number)
{
  static constexpr char kHex[] = "0123456789abcdef";
  std::string key;
  key.reserve((RMW_GID_STORAGE_SIZE * 2) + 24);
  for (size_t i = 0; i < RMW_GID_STORAGE_SIZE; ++i) {
    const std::uint8_t byte = writer_guid[i];
    key.push_back(kHex[(byte >> 4) & 0x0F]);
    key.push_back(kHex[byte & 0x0F]);
  }
  key.push_back(':');
  key += std::to_string(sequence_number);
  return key;
}

std::string request_key(const rmw_request_id_t & request_id)
{
  return request_key(request_id.writer_guid, request_id.sequence_number);
}

void fill_request_id(
  const std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> & writer_gid,
  std::int64_t sequence_id,
  rmw_request_id_t * request_id)
{
  if (request_id == nullptr) {
    return;
  }
  std::memset(request_id, 0, sizeof(*request_id));
  std::memcpy(request_id->writer_guid, writer_gid.data(), writer_gid.size());
  request_id->sequence_number = sequence_id;
}

FleetQoxServiceData * allocate_service_data(
  rcutils_allocator_t allocator,
  const char * service_name,
  const rmw_qos_profile_t * qos,
  bool is_service,
  const std::string & type_name,
  const std::string & node_name,
  const std::string & node_namespace,
  const std::string & endpoint_id,
  const std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> & endpoint_gid,
  const rosidl_typesupport_introspection_c__ServiceMembers * service_members,
  const rosidl_typesupport_introspection_cpp::ServiceMembers * cpp_service_members)
{
  if (!rcutils_allocator_is_valid(&allocator) || service_name == nullptr || qos == nullptr ||
    ((service_members == nullptr || service_members->request_members_ == nullptr ||
    service_members->response_members_ == nullptr) &&
    (cpp_service_members == nullptr || cpp_service_members->request_members_ == nullptr ||
    cpp_service_members->response_members_ == nullptr)))
  {
    return nullptr;
  }
  void * memory = allocator.allocate(sizeof(FleetQoxServiceData), allocator.state);
  if (memory == nullptr) {
    return nullptr;
  }
  auto * data = new (memory) FleetQoxServiceData{
    allocator,
    nullptr,
    *qos,
    is_service,
    type_name,
    node_name,
    node_namespace,
    endpoint_id,
    endpoint_gid,
    service_members,
    service_members == nullptr ? nullptr : service_members->request_members_,
    service_members == nullptr ? nullptr : service_members->response_members_,
    cpp_service_members,
    cpp_service_members == nullptr ? nullptr : cpp_service_members->request_members_,
    cpp_service_members == nullptr ? nullptr : cpp_service_members->response_members_,
    nullptr,
    nullptr,
    nullptr,
    nullptr,
    1,
    std::deque<rmw_fleetqox_cpp::ServiceFrame>{},
    std::deque<rmw_fleetqox_cpp::ServiceFrame>{},
    std::map<std::string, std::string>{}};
  data->service_name = rcutils_strdup(service_name, allocator);
  if (data->service_name == nullptr) {
    data->~FleetQoxServiceData();
    allocator.deallocate(memory, allocator.state);
    return nullptr;
  }
  return data;
}

void deallocate_service_data(FleetQoxServiceData * data)
{
  if (data == nullptr) {
    return;
  }
  rcutils_allocator_t allocator = data->allocator;
  if (data->service_name != nullptr && allocator.deallocate != nullptr) {
    allocator.deallocate(data->service_name, allocator.state);
  }
  data->~FleetQoxServiceData();
  allocator.deallocate(data, allocator.state);
}

bool serialize_service_message(
  const FleetQoxServiceData * data,
  bool request,
  const void * ros_message,
  std::vector<std::uint8_t> * payload)
{
  if (data == nullptr) {
    return false;
  }
  const auto * c_members = request ? data->request_members : data->response_members;
  if (c_members != nullptr) {
    return rmw_fleetqox_cpp_serialize_introspection_message(c_members, ros_message, payload);
  }
  const auto * cpp_members = request ? data->cpp_request_members : data->cpp_response_members;
  return rmw_fleetqox_cpp_serialize_introspection_cpp_message(
    cpp_members, ros_message, payload);
}

bool deserialize_service_message(
  const FleetQoxServiceData * data,
  bool request,
  const std::vector<std::uint8_t> * payload,
  void * ros_message)
{
  if (data == nullptr) {
    return false;
  }
  const auto * c_members = request ? data->request_members : data->response_members;
  if (c_members != nullptr) {
    return rmw_fleetqox_cpp_deserialize_introspection_message(c_members, payload, ros_message);
  }
  const auto * cpp_members = request ? data->cpp_request_members : data->cpp_response_members;
  return rmw_fleetqox_cpp_deserialize_introspection_cpp_message(
    cpp_members, payload, ros_message);
}

std::string ros_type_name_from_service_members(
  const rosidl_typesupport_introspection_c__ServiceMembers * members)
{
  if (members == nullptr || members->service_namespace_ == nullptr ||
    members->service_name_ == nullptr)
  {
    return "unknown";
  }
  std::string namespace_text = members->service_namespace_;
  size_t separator = 0;
  while ((separator = namespace_text.find("__", separator)) != std::string::npos) {
    namespace_text.replace(separator, 2, "/");
    separator += 1;
  }
  return namespace_text + "/" + members->service_name_;
}

const rosidl_typesupport_introspection_c__ServiceMembers * service_introspection_members(
  const rosidl_service_type_support_t * type_support)
{
  if (type_support == nullptr ||
    type_support->typesupport_identifier == nullptr ||
    std::strcmp(type_support->typesupport_identifier, rosidl_typesupport_introspection_c__identifier) != 0 ||
    type_support->data == nullptr)
  {
    return nullptr;
  }
  return static_cast<const rosidl_typesupport_introspection_c__ServiceMembers *>(type_support->data);
}

const rosidl_typesupport_introspection_c__MessageMembers * message_introspection_members(
  const rosidl_message_type_support_t * type_support)
{
  if (type_support == nullptr ||
    type_support->typesupport_identifier == nullptr ||
    std::strcmp(type_support->typesupport_identifier, rosidl_typesupport_introspection_c__identifier) != 0 ||
    type_support->data == nullptr)
  {
    return nullptr;
  }
  return static_cast<const rosidl_typesupport_introspection_c__MessageMembers *>(type_support->data);
}

const rosidl_typesupport_introspection_cpp::ServiceMembers * service_cpp_introspection_members(
  const rosidl_service_type_support_t * type_support)
{
  if (type_support == nullptr || type_support->typesupport_identifier == nullptr ||
    std::strcmp(
      type_support->typesupport_identifier,
      rosidl_typesupport_introspection_cpp::typesupport_identifier) != 0 ||
    type_support->data == nullptr)
  {
    return nullptr;
  }
  return static_cast<const rosidl_typesupport_introspection_cpp::ServiceMembers *>(
    type_support->data);
}

const rosidl_typesupport_introspection_cpp::MessageMembers * message_cpp_introspection_members(
  const rosidl_message_type_support_t * type_support)
{
  if (type_support == nullptr || type_support->typesupport_identifier == nullptr ||
    std::strcmp(
      type_support->typesupport_identifier,
      rosidl_typesupport_introspection_cpp::typesupport_identifier) != 0 ||
    type_support->data == nullptr)
  {
    return nullptr;
  }
  return static_cast<const rosidl_typesupport_introspection_cpp::MessageMembers *>(
    type_support->data);
}

const rosidl_message_type_support_t * resolve_effective_message_type_support(
  const rosidl_message_type_support_t * type_support)
{
  if (type_support == nullptr || type_support->typesupport_identifier == nullptr) {
    return type_support;
  }
  if (std::strcmp(
      type_support->typesupport_identifier,
      rosidl_typesupport_introspection_c__identifier) == 0)
  {
    return type_support;
  }
  if (std::strcmp(
      type_support->typesupport_identifier,
      rosidl_typesupport_c__typesupport_identifier) == 0)
  {
    const rosidl_message_type_support_t * resolved =
      rosidl_typesupport_c__get_message_typesupport_handle_function(
      type_support,
      rosidl_typesupport_introspection_c__identifier);
    if (resolved != nullptr) {
      return resolved;
    }
  }
  if (std::strcmp(
      type_support->typesupport_identifier,
      rosidl_typesupport_cpp::typesupport_identifier) == 0)
  {
    const rosidl_message_type_support_t * resolved =
      rosidl_typesupport_cpp::get_message_typesupport_handle_function(
      type_support,
      rosidl_typesupport_introspection_cpp::typesupport_identifier);
    if (resolved != nullptr) {
      return resolved;
    }
  }
  if (type_support->func != nullptr) {
    const rosidl_message_type_support_t * resolved =
      type_support->func(type_support, rosidl_typesupport_introspection_c__identifier);
    if (resolved != nullptr) {
      return resolved;
    }
  }
  return type_support;
}

const rosidl_service_type_support_t * resolve_effective_service_type_support(
  const rosidl_service_type_support_t * type_support)
{
  if (type_support == nullptr || type_support->typesupport_identifier == nullptr) {
    return type_support;
  }
  if (std::strcmp(
      type_support->typesupport_identifier,
      rosidl_typesupport_introspection_c__identifier) == 0)
  {
    return type_support;
  }
  if (std::strcmp(type_support->typesupport_identifier, rosidl_typesupport_c__typesupport_identifier) == 0) {
    const rosidl_service_type_support_t * resolved =
      rosidl_typesupport_c__get_service_typesupport_handle_function(
      type_support,
      rosidl_typesupport_introspection_c__identifier);
    if (resolved != nullptr) {
      return resolved;
    }
  }
  if (std::strcmp(
      type_support->typesupport_identifier,
      rosidl_typesupport_cpp::typesupport_identifier) == 0)
  {
    const rosidl_service_type_support_t * resolved =
      rosidl_typesupport_cpp::get_service_typesupport_handle_function(
      type_support,
      rosidl_typesupport_introspection_cpp::typesupport_identifier);
    if (resolved != nullptr) {
      return resolved;
    }
  }
  if (type_support->func != nullptr) {
    const rosidl_service_type_support_t * resolved =
      type_support->func(type_support, rosidl_typesupport_introspection_c__identifier);
    if (resolved != nullptr) {
      return resolved;
    }
  }
  return type_support;
}

std::string service_type_name_from_type_support(const rosidl_service_type_support_t * type_support)
{
  const auto * effective = resolve_effective_service_type_support(type_support);
  const auto * members = service_introspection_members(effective);
  if (members != nullptr) {
    return ros_type_name_from_service_members(members);
  }
  const auto * cpp_members = service_cpp_introspection_members(effective);
  if (cpp_members != nullptr && cpp_members->service_namespace_ != nullptr &&
    cpp_members->service_name_ != nullptr)
  {
    std::string namespace_text = cpp_members->service_namespace_;
    size_t separator = 0;
    while ((separator = namespace_text.find("::", separator)) != std::string::npos) {
      namespace_text.replace(separator, 2, "/");
      separator += 1;
    }
    return namespace_text + "/" + cpp_members->service_name_;
  }
  return type_support != nullptr && type_support->typesupport_identifier != nullptr ?
         type_support->typesupport_identifier : "unknown";
}

std::string endpoint_id_for_local_id(const std::string & local_id)
{
  const char * bound_endpoint = rmw_fleetqox_cpp_socket_bound_endpoint();
  if (bound_endpoint != nullptr && bound_endpoint[0] != '\0') {
    return std::string(bound_endpoint) + "|" + local_id;
  }
  return std::string("local|") + local_id;
}

std::string allocate_service_endpoint_id(bool is_service)
{
  const std::uint64_t id = is_service ?
    g_next_service_endpoint_id.fetch_add(1) :
    g_next_client_endpoint_id.fetch_add(1);
  return endpoint_id_for_local_id(std::string(is_service ? "fsvccpp-" : "fclicpp-") + std::to_string(id));
}

void send_service_graph_advertisement(const FleetQoxServiceData * data, const char * action)
{
  if (data == nullptr || action == nullptr) {
    return;
  }
  const rmw_ret_t ret = rmw_fleetqox_cpp_send_graph_advertisement(
    action,
    data->is_service ? "service" : "client",
    data->node_name.c_str(),
    data->node_namespace.c_str(),
    data->service_name,
    data->type_name.c_str(),
    data->endpoint_id.c_str(),
    &data->qos);
  (void)ret;
}

void service_graph_renewal_loop()
{
  constexpr auto kRenewInterval = std::chrono::milliseconds(500);
  while (true) {
    std::this_thread::sleep_for(kRenewInterval);
    std::lock_guard<std::mutex> lock(g_service_graph_mutex);
    for (const FleetQoxServiceData * data : g_service_graph_endpoints) {
      send_service_graph_advertisement(data, "add");
    }
  }
}

void ensure_service_graph_renewal_thread()
{
  bool expected = false;
  if (!g_service_graph_renewal_started.compare_exchange_strong(expected, true)) {
    return;
  }
  std::thread(service_graph_renewal_loop).detach();
}

void add_service_graph_renewal_endpoint(FleetQoxServiceData * data)
{
  if (data == nullptr) {
    return;
  }
  {
    std::lock_guard<std::mutex> lock(g_service_graph_mutex);
    g_service_graph_endpoints.push_back(data);
  }
  ensure_service_graph_renewal_thread();
}

void remove_service_graph_renewal_endpoint(FleetQoxServiceData * data)
{
  std::lock_guard<std::mutex> lock(g_service_graph_mutex);
  g_service_graph_endpoints.erase(
    std::remove(g_service_graph_endpoints.begin(), g_service_graph_endpoints.end(), data),
    g_service_graph_endpoints.end());
}

bool service_has_request_locked(const FleetQoxServiceData * data)
{
  return data != nullptr && data->is_service && !data->request_queue.empty();
}

bool client_has_response_locked(const FleetQoxServiceData * data)
{
  return data != nullptr && !data->is_service && !data->response_queue.empty();
}

FleetQoxServiceData * service_data_from_waitable_locked(const void * waitable)
{
  for (FleetQoxServiceData * data : g_service_bus_endpoints) {
    if (data == waitable && data->is_service) {
      return data;
    }
  }
  for (const rmw_service_t * service : g_service_handles) {
    if (service == waitable && service != nullptr) {
      return service_data(service);
    }
  }
  return nullptr;
}

FleetQoxServiceData * client_data_from_waitable_locked(const void * waitable)
{
  for (FleetQoxServiceData * data : g_service_bus_endpoints) {
    if (data == waitable && !data->is_service) {
      return data;
    }
  }
  for (const rmw_client_t * client : g_client_handles) {
    if (client == waitable && client != nullptr) {
      return client_data(client);
    }
  }
  return nullptr;
}

rmw_ret_t fill_udp_network_flow_endpoint(
  rcutils_allocator_t * allocator,
  rmw_network_flow_endpoint_array_t * endpoints)
{
  if (allocator == nullptr || !rcutils_allocator_is_valid(allocator) || endpoints == nullptr) {
    RMW_SET_ERROR_MSG("invalid allocator or network flow endpoint output");
    return RMW_RET_INVALID_ARGUMENT;
  }
  const char * transport_mode = rmw_fleetqox_cpp_transport_mode();
  if (transport_mode != nullptr && std::strcmp(transport_mode, "shm") == 0) {
    *endpoints = rmw_get_zero_initialized_network_flow_endpoint_array();
    return RMW_RET_OK;
  }
  const char * bound_endpoint = rmw_fleetqox_cpp_socket_bound_endpoint();
  if (bound_endpoint == nullptr || bound_endpoint[0] == '\0') {
    RMW_SET_ERROR_MSG("FleetRMW UDP socket has no bound endpoint");
    return RMW_RET_ERROR;
  }
  const std::string endpoint(bound_endpoint);
  const size_t separator = endpoint.rfind(':');
  if (separator == std::string::npos || separator == 0 || separator + 1 >= endpoint.size()) {
    RMW_SET_ERROR_MSG("FleetRMW UDP bound endpoint is malformed");
    return RMW_RET_ERROR;
  }
  const std::string address = endpoint.substr(0, separator);
  const std::string port_text = endpoint.substr(separator + 1);
  char * port_end = nullptr;
  errno = 0;
  const long port = std::strtol(port_text.c_str(), &port_end, 10);
  if (errno != 0 || port_end == port_text.c_str() || *port_end != '\0' ||
    port < 0 || port > 65535)
  {
    RMW_SET_ERROR_MSG("FleetRMW UDP bound endpoint port is invalid");
    return RMW_RET_ERROR;
  }
  rmw_ret_t ret = rmw_network_flow_endpoint_array_init(endpoints, 1, allocator);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  rmw_network_flow_endpoint_t & flow = endpoints->network_flow_endpoint[0];
  flow.transport_protocol = RMW_TRANSPORT_PROTOCOL_UDP;
  flow.internet_protocol = RMW_INTERNET_PROTOCOL_IPV4;
  flow.transport_port = static_cast<std::uint16_t>(port);
  flow.flow_label = 0;
  flow.dscp = 0;
  ret = rmw_network_flow_endpoint_set_internet_address(
    &flow, address.c_str(), address.size());
  if (ret != RMW_RET_OK) {
    rmw_network_flow_endpoint_array_fini(endpoints);
    return ret;
  }
  return RMW_RET_OK;
}

void fill_pointer_gid(const void * entity, rmw_gid_t * gid)
{
  std::memset(gid, 0, sizeof(*gid));
  gid->implementation_identifier = kIdentifier;
  const auto value = reinterpret_cast<std::uintptr_t>(entity);
  const size_t copy_size = std::min(sizeof(value), static_cast<size_t>(RMW_GID_STORAGE_SIZE));
  std::memcpy(gid->data, &value, copy_size);
}

void clear_reason(char * reason, size_t reason_size)
{
  if (reason != nullptr && reason_size > 0) {
    reason[0] = '\0';
  }
}

}  // namespace

extern "C"
{

bool rmw_fleetqox_cpp_handle_service_frame(const char * encoded_frame, size_t size)
{
  if (encoded_frame == nullptr || size == 0) {
    return false;
  }
  const auto frame = rmw_fleetqox_cpp::decode_service_frame(std::string(encoded_frame, size));
  if (!frame) {
    return false;
  }
  if (drop_if_expired_service_frame(*frame)) {
    return true;
  }
  std::vector<std::pair<rmw_event_callback_t, const void *>> callbacks;
  {
    std::lock_guard<std::mutex> lock(g_service_bus_mutex);
    if (frame->role == "request") {
      for (FleetQoxServiceData * data : g_service_bus_endpoints) {
        if (data != nullptr && data->is_service && data->service_name != nullptr &&
          frame->service_name == data->service_name)
        {
          data->request_queue.push_back(*frame);
          trace_service_event("enqueue_request", data, &*frame, data->request_queue.size());
          if (data->on_new_request_callback != nullptr) {
            callbacks.emplace_back(
              data->on_new_request_callback, data->on_new_request_user_data);
          }
        }
      }
    } else if (frame->role == "response") {
      for (FleetQoxServiceData * data : g_service_bus_endpoints) {
        if (data != nullptr && !data->is_service &&
          frame->client_endpoint_id == data->endpoint_id)
        {
          data->response_queue.push_back(*frame);
          trace_service_event("enqueue_response", data, &*frame, data->response_queue.size());
          if (data->on_new_response_callback != nullptr) {
            callbacks.emplace_back(
              data->on_new_response_callback, data->on_new_response_user_data);
          }
        }
      }
    }
  }
  for (const auto & callback : callbacks) {
    callback.first(callback.second, 1);
  }
  return true;
}

bool rmw_fleetqox_cpp_waitable_service_has_request(const void * waitable)
{
  if (waitable == nullptr) {
    return false;
  }
  std::lock_guard<std::mutex> lock(g_service_bus_mutex);
  return service_has_request_locked(service_data_from_waitable_locked(waitable));
}

bool rmw_fleetqox_cpp_waitable_client_has_response(const void * waitable)
{
  if (waitable == nullptr) {
    return false;
  }
  std::lock_guard<std::mutex> lock(g_service_bus_mutex);
  FleetQoxServiceData * matched = client_data_from_waitable_locked(waitable);
  if (matched == nullptr && trace_service_enabled()) {
    for (FleetQoxServiceData * data : g_service_bus_endpoints) {
      if (client_has_response_locked(data)) {
        std::fprintf(
          stderr,
          "fleetqox service event=waitable_client_unmatched waitable=%p pending_data=%p endpoint=%s\n",
          waitable,
          static_cast<void *>(data),
          data->endpoint_id.c_str());
        break;
      }
    }
  }
  return client_has_response_locked(matched);
}

std::uint64_t rmw_fleetqox_cpp_service_expired_frames_dropped()
{
  return g_service_expired_frames_dropped.load();
}

const char * rmw_fleetqox_cpp_service_endpoint_id(const rmw_service_t * service)
{
  const FleetQoxServiceData * data = service_data(service);
  return data == nullptr ? "" : data->endpoint_id.c_str();
}

const char * rmw_fleetqox_cpp_client_endpoint_id(const rmw_client_t * client)
{
  const FleetQoxServiceData * data = client_data(client);
  return data == nullptr ? "" : data->endpoint_id.c_str();
}

rmw_ret_t rmw_init_publisher_allocation(
  const rosidl_message_type_support_t * type_support,
  const rosidl_runtime_c__Sequence__bound * message_bounds,
  rmw_publisher_allocation_t * allocation)
{
  (void)message_bounds;
  if (type_support == nullptr || allocation == nullptr) {
    RMW_SET_ERROR_MSG("publisher allocation arguments must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return unsupported("publisher allocations are not supported by rmw_fleetqox_cpp yet");
}

rmw_ret_t rmw_fini_publisher_allocation(rmw_publisher_allocation_t * allocation)
{
  if (allocation == nullptr) {
    RMW_SET_ERROR_MSG("publisher allocation is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return RMW_RET_OK;
}

rmw_ret_t rmw_borrow_loaned_message(
  const rmw_publisher_t * publisher,
  const rosidl_message_type_support_t * type_support,
  void ** ros_message)
{
  rmw_ret_t ret = validate_publisher(publisher);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (type_support == nullptr || ros_message == nullptr || *ros_message != nullptr) {
    RMW_SET_ERROR_MSG("loaned publisher message arguments are invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return rmw_fleetqox_cpp_borrow_publisher_loan(publisher, type_support, ros_message);
}

rmw_ret_t rmw_return_loaned_message_from_publisher(
  const rmw_publisher_t * publisher,
  void * loaned_message)
{
  rmw_ret_t ret = validate_publisher(publisher);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (loaned_message == nullptr) {
    RMW_SET_ERROR_MSG("loaned publisher message is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return rmw_fleetqox_cpp_release_publisher_loan(publisher, loaned_message);
}

rmw_ret_t rmw_publish_loaned_message(
  const rmw_publisher_t * publisher,
  void * ros_message,
  rmw_publisher_allocation_t * allocation)
{
  (void)allocation;
  rmw_ret_t ret = validate_publisher(publisher);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (ros_message == nullptr) {
    RMW_SET_ERROR_MSG("loaned publisher message is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  ret = rmw_publish(publisher, ros_message, allocation);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  return rmw_fleetqox_cpp_release_publisher_loan(publisher, ros_message);
}

rmw_ret_t rmw_publisher_event_init(
  rmw_event_t * rmw_event,
  const rmw_publisher_t * publisher,
  rmw_event_type_t event_type)
{
  (void)event_type;
  if (rmw_event == nullptr) {
    RMW_SET_ERROR_MSG("publisher event is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = validate_publisher(publisher);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  return unsupported("publisher events are not supported by rmw_fleetqox_cpp yet");
}

rmw_ret_t rmw_publisher_assert_liveliness(const rmw_publisher_t * publisher)
{
  rmw_ret_t ret = validate_publisher(publisher);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  return RMW_RET_OK;
}

rmw_ret_t rmw_publisher_wait_for_all_acked(
  const rmw_publisher_t * publisher,
  rmw_time_t wait_timeout)
{
  (void)wait_timeout;
  rmw_ret_t ret = validate_publisher(publisher);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  return RMW_RET_OK;
}

rmw_ret_t rmw_get_serialized_message_size(
  const rosidl_message_type_support_t * type_support,
  const rosidl_runtime_c__Sequence__bound * message_bounds,
  size_t * size)
{
  (void)message_bounds;
  if (type_support == nullptr || size == nullptr) {
    RMW_SET_ERROR_MSG("serialized message size arguments must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  const auto * effective = resolve_effective_message_type_support(type_support);
  const auto * members = message_introspection_members(effective);
  const auto * cpp_members = message_cpp_introspection_members(effective);
  if (members == nullptr && cpp_members == nullptr) {
    return unsupported(
      "standalone serialization sizing requires introspection C or C++ type support");
  }
  const bool computed = members != nullptr ?
    rmw_fleetqox_cpp_max_serialized_size_introspection_message(members, size) :
    rmw_fleetqox_cpp_max_serialized_size_introspection_cpp_message(cpp_members, size);
  if (!computed) {
    return unsupported(
      "standalone serialization sizing requires a statically bounded message type");
  }
  return RMW_RET_OK;
}

rmw_ret_t rmw_serialize(
  const void * ros_message,
  const rosidl_message_type_support_t * type_support,
  rmw_serialized_message_t * serialized_message)
{
  if (ros_message == nullptr || type_support == nullptr || serialized_message == nullptr) {
    RMW_SET_ERROR_MSG("serialize arguments must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  const auto * effective = resolve_effective_message_type_support(type_support);
  const auto * members = message_introspection_members(effective);
  const auto * cpp_members = message_cpp_introspection_members(effective);
  if (members == nullptr && cpp_members == nullptr) {
    RMW_SET_ERROR_MSG("rmw_serialize requires introspection C or C++ type support");
    return RMW_RET_UNSUPPORTED;
  }
  std::vector<std::uint8_t> payload;
  const bool serialized = members != nullptr ?
    rmw_fleetqox_cpp_serialize_introspection_message(members, ros_message, &payload) :
    rmw_fleetqox_cpp_serialize_introspection_cpp_message(cpp_members, ros_message, &payload);
  if (!serialized) {
    RMW_SET_ERROR_MSG("failed to serialize message with introspection type support");
    return RMW_RET_ERROR;
  }
  if (payload.size() > serialized_message->buffer_capacity) {
    const rmw_ret_t resize_ret = rmw_serialized_message_resize(serialized_message, payload.size());
    if (resize_ret != RMW_RET_OK) {
      RMW_SET_ERROR_MSG("failed to resize standalone serialized message");
      return resize_ret;
    }
  }
  if (!payload.empty()) {
    std::memcpy(serialized_message->buffer, payload.data(), payload.size());
  }
  serialized_message->buffer_length = payload.size();
  return RMW_RET_OK;
}

rmw_ret_t rmw_deserialize(
  const rmw_serialized_message_t * serialized_message,
  const rosidl_message_type_support_t * type_support,
  void * ros_message)
{
  if (serialized_message == nullptr || type_support == nullptr || ros_message == nullptr) {
    RMW_SET_ERROR_MSG("deserialize arguments must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  if (serialized_message->buffer_length > serialized_message->buffer_capacity ||
    (serialized_message->buffer_length > 0 && serialized_message->buffer == nullptr))
  {
    RMW_SET_ERROR_MSG("serialized message buffer is invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  const auto * effective = resolve_effective_message_type_support(type_support);
  const auto * members = message_introspection_members(effective);
  const auto * cpp_members = message_cpp_introspection_members(effective);
  if (members == nullptr && cpp_members == nullptr) {
    RMW_SET_ERROR_MSG("rmw_deserialize requires introspection C or C++ type support");
    return RMW_RET_UNSUPPORTED;
  }
  std::vector<std::uint8_t> payload;
  if (serialized_message->buffer_length > 0) {
    payload.assign(
      serialized_message->buffer,
      serialized_message->buffer + serialized_message->buffer_length);
  }
  const bool deserialized = members != nullptr ?
    rmw_fleetqox_cpp_deserialize_introspection_message(members, &payload, ros_message) :
    rmw_fleetqox_cpp_deserialize_introspection_cpp_message(cpp_members, &payload, ros_message);
  if (!deserialized) {
    RMW_SET_ERROR_MSG("failed to deserialize message with introspection type support");
    return RMW_RET_ERROR;
  }
  return RMW_RET_OK;
}

rmw_ret_t rmw_init_subscription_allocation(
  const rosidl_message_type_support_t * type_support,
  const rosidl_runtime_c__Sequence__bound * message_bounds,
  rmw_subscription_allocation_t * allocation)
{
  (void)message_bounds;
  if (type_support == nullptr || allocation == nullptr) {
    RMW_SET_ERROR_MSG("subscription allocation arguments must be non-null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return unsupported("subscription allocations are not supported by rmw_fleetqox_cpp yet");
}

rmw_ret_t rmw_fini_subscription_allocation(rmw_subscription_allocation_t * allocation)
{
  if (allocation == nullptr) {
    RMW_SET_ERROR_MSG("subscription allocation is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return RMW_RET_OK;
}

rmw_ret_t rmw_subscription_event_init(
  rmw_event_t * rmw_event,
  const rmw_subscription_t * subscription,
  rmw_event_type_t event_type)
{
  (void)event_type;
  if (rmw_event == nullptr) {
    RMW_SET_ERROR_MSG("subscription event is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_ret_t ret = validate_subscription(subscription);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  return unsupported("subscription events are not supported by rmw_fleetqox_cpp yet");
}

rmw_ret_t rmw_subscription_set_content_filter(
  rmw_subscription_t * subscription,
  const rmw_subscription_content_filter_options_t * options)
{
  rmw_ret_t ret = validate_subscription(subscription);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (options == nullptr) {
    RMW_SET_ERROR_MSG("content filter options are null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return unsupported("content filtered topics are not supported by rmw_fleetqox_cpp yet");
}

rmw_ret_t rmw_subscription_get_content_filter(
  const rmw_subscription_t * subscription,
  rcutils_allocator_t * allocator,
  rmw_subscription_content_filter_options_t * options)
{
  rmw_ret_t ret = validate_subscription(subscription);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (allocator == nullptr || !rcutils_allocator_is_valid(allocator) || options == nullptr) {
    RMW_SET_ERROR_MSG("content filter output arguments are invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return unsupported("content filtered topics are not supported by rmw_fleetqox_cpp yet");
}

rmw_ret_t rmw_take_loaned_message(
  const rmw_subscription_t * subscription,
  void ** loaned_message,
  bool * taken,
  rmw_subscription_allocation_t * allocation)
{
  (void)allocation;
  rmw_ret_t ret = validate_subscription(subscription);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (loaned_message == nullptr || taken == nullptr) {
    RMW_SET_ERROR_MSG("loaned subscription message arguments are invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  if (*loaned_message != nullptr) {
    RMW_SET_ERROR_MSG("loaned subscription message output must be null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  *taken = false;
  ret = rmw_fleetqox_cpp_borrow_subscription_loan(subscription, loaned_message);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  ret = rmw_take(subscription, *loaned_message, taken, allocation);
  if (ret != RMW_RET_OK || !*taken) {
    const rmw_ret_t release_ret =
      rmw_fleetqox_cpp_release_subscription_loan(subscription, *loaned_message);
    *loaned_message = nullptr;
    return ret != RMW_RET_OK ? ret : release_ret;
  }
  return RMW_RET_OK;
}

rmw_ret_t rmw_take_loaned_message_with_info(
  const rmw_subscription_t * subscription,
  void ** loaned_message,
  bool * taken,
  rmw_message_info_t * message_info,
  rmw_subscription_allocation_t * allocation)
{
  rmw_ret_t ret = validate_subscription(subscription);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (loaned_message == nullptr || taken == nullptr || message_info == nullptr ||
    *loaned_message != nullptr)
  {
    RMW_SET_ERROR_MSG("loaned subscription message-with-info arguments are invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  *taken = false;
  ret = rmw_fleetqox_cpp_borrow_subscription_loan(subscription, loaned_message);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  ret = rmw_take_with_info(subscription, *loaned_message, taken, message_info, allocation);
  if (ret != RMW_RET_OK || !*taken) {
    const rmw_ret_t release_ret =
      rmw_fleetqox_cpp_release_subscription_loan(subscription, *loaned_message);
    *loaned_message = nullptr;
    return ret != RMW_RET_OK ? ret : release_ret;
  }
  return RMW_RET_OK;
}

rmw_ret_t rmw_return_loaned_message_from_subscription(
  const rmw_subscription_t * subscription,
  void * loaned_message)
{
  rmw_ret_t ret = validate_subscription(subscription);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (loaned_message == nullptr) {
    RMW_SET_ERROR_MSG("loaned subscription message is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return rmw_fleetqox_cpp_release_subscription_loan(subscription, loaned_message);
}

rmw_client_t * rmw_create_client(
  const rmw_node_t * node,
  const rosidl_service_type_support_t * type_support,
  const char * service_name,
  const rmw_qos_profile_t * qos_policies)
{
  rmw_ret_t ret = validate_node(node);
  if (ret != RMW_RET_OK) {
    return nullptr;
  }
  if (type_support == nullptr || service_name == nullptr || qos_policies == nullptr) {
    RMW_SET_ERROR_MSG("client creation arguments are invalid");
    return nullptr;
  }
  rmw_client_t * client = rmw_client_allocate();
  if (client == nullptr) {
    RMW_SET_ERROR_MSG("failed to allocate client handle");
    return nullptr;
  }
  const rosidl_service_type_support_t * effective_type_support =
    resolve_effective_service_type_support(type_support);
  const auto * service_members = service_introspection_members(effective_type_support);
  const auto * cpp_service_members = service_cpp_introspection_members(effective_type_support);
  if (service_members == nullptr && cpp_service_members == nullptr) {
    rmw_client_free(client);
    RMW_SET_ERROR_MSG("client requires introspection C or C++ service type support");
    return nullptr;
  }
  const std::string type_name = service_type_name_from_type_support(effective_type_support);
  const std::string endpoint_id = allocate_service_endpoint_id(false);
  const std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> endpoint_gid =
    endpoint_gid_from_id(endpoint_id);
  FleetQoxServiceData * data =
    allocate_service_data(
    node->context->options.allocator,
    service_name,
    qos_policies,
    false,
    type_name,
    std::string(node->name != nullptr ? node->name : ""),
    std::string(node->namespace_ != nullptr ? node->namespace_ : ""),
    endpoint_id,
    endpoint_gid,
    service_members,
    cpp_service_members);
  if (data == nullptr) {
    rmw_client_free(client);
    RMW_SET_ERROR_MSG("failed to allocate client data");
    return nullptr;
  }
  client->implementation_identifier = kIdentifier;
  client->data = data;
  client->service_name = data->service_name;
  {
    std::lock_guard<std::mutex> lock(g_service_bus_mutex);
    g_service_bus_endpoints.push_back(data);
    g_client_handles.push_back(client);
  }
  rmw_fleetqox_cpp_graph_register_client_endpoint(
    data->node_name.c_str(),
    data->node_namespace.c_str(),
    data->service_name,
    data->type_name.c_str(),
    data->endpoint_id.c_str());
  add_service_graph_renewal_endpoint(data);
  send_service_graph_advertisement(data, "add");
  return client;
}

rmw_ret_t rmw_destroy_client(rmw_node_t * node, rmw_client_t * client)
{
  rmw_ret_t ret = validate_node(node);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  ret = validate_client(client);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxServiceData * data = client_data(client);
  if (data != nullptr) {
    {
      std::lock_guard<std::mutex> lock(g_service_bus_mutex);
      g_service_bus_endpoints.erase(
        std::remove(g_service_bus_endpoints.begin(), g_service_bus_endpoints.end(), data),
        g_service_bus_endpoints.end());
      g_client_handles.erase(
        std::remove(g_client_handles.begin(), g_client_handles.end(), client),
        g_client_handles.end());
    }
    remove_service_graph_renewal_endpoint(data);
    rmw_fleetqox_cpp_graph_unregister_client_endpoint(data->endpoint_id.c_str());
    send_service_graph_advertisement(data, "remove");
  }
  deallocate_service_data(data);
  rmw_client_free(client);
  return RMW_RET_OK;
}

rmw_ret_t rmw_send_request(
  const rmw_client_t * client,
  const void * ros_request,
  int64_t * sequence_id)
{
  rmw_ret_t ret = validate_client(client);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (ros_request == nullptr || sequence_id == nullptr) {
    RMW_SET_ERROR_MSG("request arguments are invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  FleetQoxServiceData * data = client_data(client);
  if (data == nullptr || data->service_name == nullptr ||
    (data->request_members == nullptr && data->cpp_request_members == nullptr))
  {
    RMW_SET_ERROR_MSG("client data is invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  std::vector<std::uint8_t> payload;
  if (!serialize_service_message(data, true, ros_request, &payload)) {
    RMW_SET_ERROR_MSG("failed to serialize service request with introspection type support");
    return RMW_RET_UNSUPPORTED;
  }
  std::int64_t next_sequence = 0;
  {
    std::lock_guard<std::mutex> lock(g_service_bus_mutex);
    next_sequence = data->next_sequence_id++;
  }
  const rmw_fleetqox_cpp::ServiceFrame frame{
    "request",
    data->service_name,
    data->type_name,
    data->endpoint_id,
    "",
    next_sequence,
    monotonic_timestamp_ns(),
    qos_duration_ns(data->qos.lifespan),
    payload};
  trace_service_event("send_request", data, &frame);
  const std::string encoded = rmw_fleetqox_cpp::encode_service_frame(frame);
  ret = rmw_fleetqox_cpp_send_encoded_frame(encoded.data(), encoded.size());
  if (ret != RMW_RET_OK) {
    return ret;
  }
  *sequence_id = next_sequence;
  return RMW_RET_OK;
}

rmw_ret_t rmw_take_response(
  const rmw_client_t * client,
  rmw_service_info_t * request_header,
  void * ros_response,
  bool * taken)
{
  rmw_ret_t ret = validate_client(client);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (request_header == nullptr || ros_response == nullptr || taken == nullptr) {
    RMW_SET_ERROR_MSG("response take arguments are invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  FleetQoxServiceData * data = client_data(client);
  if (data == nullptr ||
    (data->response_members == nullptr && data->cpp_response_members == nullptr))
  {
    RMW_SET_ERROR_MSG("client data is invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_fleetqox_cpp::ServiceFrame frame{};
  {
    std::lock_guard<std::mutex> lock(g_service_bus_mutex);
    while (!data->response_queue.empty()) {
      frame = std::move(data->response_queue.front());
      data->response_queue.pop_front();
      if (drop_if_expired_service_frame(frame)) {
        frame = rmw_fleetqox_cpp::ServiceFrame{};
        continue;
      }
      break;
    }
    if (frame.role.empty()) {
      *taken = false;
      return RMW_RET_OK;
    }
  }
  if (!deserialize_service_message(data, false, &frame.serialized_payload, ros_response))
  {
    *taken = false;
    trace_service_event("take_response_deserialize_failed", data, &frame);
    RMW_SET_ERROR_MSG("failed to deserialize service response with introspection type support");
    return RMW_RET_UNSUPPORTED;
  }
  request_header->source_timestamp = frame.source_timestamp_ns;
  request_header->received_timestamp = monotonic_timestamp_ns();
  fill_request_id(data->endpoint_gid, frame.sequence_id, &request_header->request_id);
  *taken = true;
  trace_service_event("take_response", data, &frame);
  return RMW_RET_OK;
}

rmw_ret_t rmw_fleetqox_cpp_send_malformed_response(
  const rmw_service_t * service,
  rmw_request_id_t * request_header)
{
  rmw_ret_t ret = validate_service(service);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (request_header == nullptr) {
    RMW_SET_ERROR_MSG("malformed response request header is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  FleetQoxServiceData * data = service_data(service);
  if (data == nullptr || data->service_name == nullptr) {
    RMW_SET_ERROR_MSG("service data is invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  std::string client_endpoint_id;
  {
    std::lock_guard<std::mutex> lock(g_service_bus_mutex);
    const auto found = data->pending_response_clients.find(request_key(*request_header));
    if (found != data->pending_response_clients.end()) {
      client_endpoint_id = found->second;
      data->pending_response_clients.erase(found);
    }
  }
  if (client_endpoint_id.empty()) {
    trace_service_event("send_malformed_response_unknown_target", data);
    RMW_SET_ERROR_MSG("malformed service response target is unknown");
    return RMW_RET_ERROR;
  }
  const rmw_fleetqox_cpp::ServiceFrame frame{
    "response",
    data->service_name,
    data->type_name,
    client_endpoint_id,
    data->endpoint_id,
    request_header->sequence_number,
    monotonic_timestamp_ns(),
    qos_duration_ns(data->qos.lifespan),
    std::vector<std::uint8_t>{0xff}};
  trace_service_event("send_malformed_response", data, &frame);
  const std::string encoded = rmw_fleetqox_cpp::encode_service_frame(frame);
  return rmw_fleetqox_cpp_send_encoded_frame(encoded.data(), encoded.size());
}

rmw_service_t * rmw_create_service(
  const rmw_node_t * node,
  const rosidl_service_type_support_t * type_support,
  const char * service_name,
  const rmw_qos_profile_t * qos_profile)
{
  rmw_ret_t ret = validate_node(node);
  if (ret != RMW_RET_OK) {
    return nullptr;
  }
  if (type_support == nullptr || service_name == nullptr || qos_profile == nullptr) {
    RMW_SET_ERROR_MSG("service creation arguments are invalid");
    return nullptr;
  }
  rmw_service_t * service = rmw_service_allocate();
  if (service == nullptr) {
    RMW_SET_ERROR_MSG("failed to allocate service handle");
    return nullptr;
  }
  const rosidl_service_type_support_t * effective_type_support =
    resolve_effective_service_type_support(type_support);
  const auto * service_members = service_introspection_members(effective_type_support);
  const auto * cpp_service_members = service_cpp_introspection_members(effective_type_support);
  if (service_members == nullptr && cpp_service_members == nullptr) {
    rmw_service_free(service);
    RMW_SET_ERROR_MSG("service requires introspection C or C++ service type support");
    return nullptr;
  }
  const std::string type_name = service_type_name_from_type_support(effective_type_support);
  const std::string endpoint_id = allocate_service_endpoint_id(true);
  const std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> endpoint_gid =
    endpoint_gid_from_id(endpoint_id);
  FleetQoxServiceData * data =
    allocate_service_data(
    node->context->options.allocator,
    service_name,
    qos_profile,
    true,
    type_name,
    std::string(node->name != nullptr ? node->name : ""),
    std::string(node->namespace_ != nullptr ? node->namespace_ : ""),
    endpoint_id,
    endpoint_gid,
    service_members,
    cpp_service_members);
  if (data == nullptr) {
    rmw_service_free(service);
    RMW_SET_ERROR_MSG("failed to allocate service data");
    return nullptr;
  }
  service->implementation_identifier = kIdentifier;
  service->data = data;
  service->service_name = data->service_name;
  {
    std::lock_guard<std::mutex> lock(g_service_bus_mutex);
    g_service_bus_endpoints.push_back(data);
    g_service_handles.push_back(service);
  }
  rmw_fleetqox_cpp_graph_register_service_endpoint(
    data->node_name.c_str(),
    data->node_namespace.c_str(),
    data->service_name,
    data->type_name.c_str(),
    data->endpoint_id.c_str());
  add_service_graph_renewal_endpoint(data);
  send_service_graph_advertisement(data, "add");
  return service;
}

rmw_ret_t rmw_destroy_service(rmw_node_t * node, rmw_service_t * service)
{
  rmw_ret_t ret = validate_node(node);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  ret = validate_service(service);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxServiceData * data = service_data(service);
  if (data != nullptr) {
    {
      std::lock_guard<std::mutex> lock(g_service_bus_mutex);
      g_service_bus_endpoints.erase(
        std::remove(g_service_bus_endpoints.begin(), g_service_bus_endpoints.end(), data),
        g_service_bus_endpoints.end());
      g_service_handles.erase(
        std::remove(g_service_handles.begin(), g_service_handles.end(), service),
        g_service_handles.end());
    }
    remove_service_graph_renewal_endpoint(data);
    rmw_fleetqox_cpp_graph_unregister_service_endpoint(data->endpoint_id.c_str());
    send_service_graph_advertisement(data, "remove");
  }
  deallocate_service_data(data);
  rmw_service_free(service);
  return RMW_RET_OK;
}

rmw_ret_t rmw_take_request(
  const rmw_service_t * service,
  rmw_service_info_t * request_header,
  void * ros_request,
  bool * taken)
{
  rmw_ret_t ret = validate_service(service);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (request_header == nullptr || ros_request == nullptr || taken == nullptr) {
    RMW_SET_ERROR_MSG("request take arguments are invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  FleetQoxServiceData * data = service_data(service);
  if (data == nullptr ||
    (data->request_members == nullptr && data->cpp_request_members == nullptr))
  {
    RMW_SET_ERROR_MSG("service data is invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  rmw_fleetqox_cpp::ServiceFrame frame{};
  {
    std::lock_guard<std::mutex> lock(g_service_bus_mutex);
    while (!data->request_queue.empty()) {
      frame = std::move(data->request_queue.front());
      data->request_queue.pop_front();
      if (drop_if_expired_service_frame(frame)) {
        frame = rmw_fleetqox_cpp::ServiceFrame{};
        continue;
      }
      break;
    }
    if (frame.role.empty()) {
      *taken = false;
      return RMW_RET_OK;
    }
  }
  if (!deserialize_service_message(data, true, &frame.serialized_payload, ros_request))
  {
    *taken = false;
    trace_service_event("take_request_deserialize_failed", data, &frame);
    RMW_SET_ERROR_MSG("failed to deserialize service request with introspection type support");
    return RMW_RET_UNSUPPORTED;
  }
  const std::array<std::uint8_t, RMW_GID_STORAGE_SIZE> client_gid =
    endpoint_gid_from_id(frame.client_endpoint_id);
  request_header->source_timestamp = frame.source_timestamp_ns;
  request_header->received_timestamp = monotonic_timestamp_ns();
  fill_request_id(client_gid, frame.sequence_id, &request_header->request_id);
  {
    std::lock_guard<std::mutex> lock(g_service_bus_mutex);
    data->pending_response_clients[request_key(request_header->request_id)] = frame.client_endpoint_id;
  }
  *taken = true;
  trace_service_event("take_request", data, &frame);
  return RMW_RET_OK;
}

rmw_ret_t rmw_send_response(
  const rmw_service_t * service,
  rmw_request_id_t * request_header,
  void * ros_response)
{
  rmw_ret_t ret = validate_service(service);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (request_header == nullptr || ros_response == nullptr) {
    RMW_SET_ERROR_MSG("response send arguments are invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  FleetQoxServiceData * data = service_data(service);
  if (data == nullptr || data->service_name == nullptr ||
    (data->response_members == nullptr && data->cpp_response_members == nullptr))
  {
    RMW_SET_ERROR_MSG("service data is invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  std::vector<std::uint8_t> payload;
  if (!serialize_service_message(data, false, ros_response, &payload)) {
    trace_service_event("send_response_serialize_failed", data);
    RMW_SET_ERROR_MSG("failed to serialize service response with introspection type support");
    return RMW_RET_UNSUPPORTED;
  }
  std::string client_endpoint_id;
  {
    std::lock_guard<std::mutex> lock(g_service_bus_mutex);
    const auto found = data->pending_response_clients.find(request_key(*request_header));
    if (found != data->pending_response_clients.end()) {
      client_endpoint_id = found->second;
      data->pending_response_clients.erase(found);
    }
  }
  if (client_endpoint_id.empty()) {
    trace_service_event("send_response_unknown_target", data);
    RMW_SET_ERROR_MSG("service response target is unknown");
    return RMW_RET_ERROR;
  }
  const rmw_fleetqox_cpp::ServiceFrame frame{
    "response",
    data->service_name,
    data->type_name,
    client_endpoint_id,
    data->endpoint_id,
    request_header->sequence_number,
    monotonic_timestamp_ns(),
    qos_duration_ns(data->qos.lifespan),
    payload};
  trace_service_event("send_response", data, &frame);
  const std::string encoded = rmw_fleetqox_cpp::encode_service_frame(frame);
  return rmw_fleetqox_cpp_send_encoded_frame(encoded.data(), encoded.size());
}

rmw_ret_t rmw_take_event(const rmw_event_t * event_handle, void * event_info, bool * taken)
{
  if (event_handle == nullptr || event_info == nullptr || taken == nullptr) {
    RMW_SET_ERROR_MSG("event take arguments are invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  if (!identifier_matches(event_handle->implementation_identifier)) {
    RMW_SET_ERROR_MSG("event is not from rmw_fleetqox_cpp");
    return RMW_RET_INCORRECT_RMW_IMPLEMENTATION;
  }
  *taken = false;
  return unsupported("events are not supported by rmw_fleetqox_cpp yet");
}

bool rmw_event_type_is_supported(rmw_event_type_t rmw_event_type)
{
  (void)rmw_event_type;
  return false;
}

rmw_ret_t rmw_get_gid_for_client(const rmw_client_t * client, rmw_gid_t * gid)
{
  rmw_ret_t ret = validate_client(client);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (gid == nullptr) {
    RMW_SET_ERROR_MSG("client gid output is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  fill_pointer_gid(client, gid);
  return RMW_RET_OK;
}

rmw_ret_t rmw_get_gid_for_publisher(const rmw_publisher_t * publisher, rmw_gid_t * gid)
{
  rmw_ret_t ret = validate_publisher(publisher);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (gid == nullptr) {
    RMW_SET_ERROR_MSG("publisher gid output is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  if (!rmw_fleetqox_cpp_publisher_gid(publisher, gid)) {
    fill_pointer_gid(publisher, gid);
  }
  return RMW_RET_OK;
}

rmw_ret_t rmw_compare_gids_equal(const rmw_gid_t * gid1, const rmw_gid_t * gid2, bool * result)
{
  if (gid1 == nullptr || gid2 == nullptr || result == nullptr) {
    RMW_SET_ERROR_MSG("gid comparison arguments are invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  if (!identifier_matches(gid1->implementation_identifier) ||
    !identifier_matches(gid2->implementation_identifier))
  {
    RMW_SET_ERROR_MSG("gid is not from rmw_fleetqox_cpp");
    return RMW_RET_INCORRECT_RMW_IMPLEMENTATION;
  }
  *result = std::memcmp(gid1->data, gid2->data, RMW_GID_STORAGE_SIZE) == 0;
  return RMW_RET_OK;
}

rmw_ret_t rmw_service_response_publisher_get_actual_qos(
  const rmw_service_t * service,
  rmw_qos_profile_t * qos)
{
  rmw_ret_t ret = validate_service(service);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (qos == nullptr) {
    RMW_SET_ERROR_MSG("service qos output is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  FleetQoxServiceData * data = service_data(service);
  if (data == nullptr) {
    RMW_SET_ERROR_MSG("service data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  *qos = data->qos;
  return RMW_RET_OK;
}

rmw_ret_t rmw_service_request_subscription_get_actual_qos(
  const rmw_service_t * service,
  rmw_qos_profile_t * qos)
{
  return rmw_service_response_publisher_get_actual_qos(service, qos);
}

rmw_ret_t rmw_service_server_is_available(
  const rmw_node_t * node,
  const rmw_client_t * client,
  bool * is_available)
{
  rmw_ret_t ret = validate_node(node);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  ret = validate_client(client);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (is_available == nullptr) {
    RMW_SET_ERROR_MSG("service availability output is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  FleetQoxServiceData * data = client_data(client);
  if (data == nullptr || data->service_name == nullptr) {
    RMW_SET_ERROR_MSG("client data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  const size_t service_count = rmw_fleetqox_cpp_graph_service_count(data->service_name);
  *is_available = service_count > 0;
  if (trace_service_enabled()) {
    std::fprintf(
      stderr,
      "fleetqox service event=server_is_available service=%s endpoint=%s count=%zu available=%s\n",
      data->service_name,
      data->endpoint_id.c_str(),
      service_count,
      *is_available ? "true" : "false");
  }
  return RMW_RET_OK;
}

rmw_ret_t rmw_set_log_severity(rmw_log_severity_t severity)
{
  (void)severity;
  return RMW_RET_OK;
}

rmw_ret_t rmw_qos_profile_check_compatible(
  const rmw_qos_profile_t publisher_profile,
  const rmw_qos_profile_t subscription_profile,
  rmw_qos_compatibility_type_t * compatibility,
  char * reason,
  size_t reason_size)
{
  if (compatibility == nullptr || (reason == nullptr && reason_size != 0)) {
    RMW_SET_ERROR_MSG("QoS compatibility output arguments are invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  *compatibility = RMW_QOS_COMPATIBILITY_OK;
  clear_reason(reason, reason_size);
  if (publisher_profile.reliability == RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT &&
    subscription_profile.reliability == RMW_QOS_POLICY_RELIABILITY_RELIABLE)
  {
    *compatibility = RMW_QOS_COMPATIBILITY_ERROR;
    if (reason != nullptr && reason_size > 0) {
      std::strncpy(reason, "reliable subscription cannot be satisfied by best-effort publisher", reason_size - 1);
      reason[reason_size - 1] = '\0';
    }
  }
  if (publisher_profile.durability == RMW_QOS_POLICY_DURABILITY_VOLATILE &&
    subscription_profile.durability == RMW_QOS_POLICY_DURABILITY_TRANSIENT_LOCAL)
  {
    *compatibility = RMW_QOS_COMPATIBILITY_ERROR;
    if (reason != nullptr && reason_size > 0) {
      std::strncpy(reason, "transient-local subscription cannot be satisfied by volatile publisher", reason_size - 1);
      reason[reason_size - 1] = '\0';
    }
  }
  return RMW_RET_OK;
}

rmw_ret_t rmw_publisher_get_network_flow_endpoints(
  const rmw_publisher_t * publisher,
  rcutils_allocator_t * allocator,
  rmw_network_flow_endpoint_array_t * network_flow_endpoint_array)
{
  rmw_ret_t ret = validate_publisher(publisher);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  return fill_udp_network_flow_endpoint(allocator, network_flow_endpoint_array);
}

rmw_ret_t rmw_subscription_get_network_flow_endpoints(
  const rmw_subscription_t * subscription,
  rcutils_allocator_t * allocator,
  rmw_network_flow_endpoint_array_t * network_flow_endpoint_array)
{
  rmw_ret_t ret = validate_subscription(subscription);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  return fill_udp_network_flow_endpoint(allocator, network_flow_endpoint_array);
}

rmw_ret_t rmw_client_request_publisher_get_actual_qos(
  const rmw_client_t * client,
  rmw_qos_profile_t * qos)
{
  rmw_ret_t ret = validate_client(client);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (qos == nullptr) {
    RMW_SET_ERROR_MSG("client qos output is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  FleetQoxServiceData * data = client_data(client);
  if (data == nullptr) {
    RMW_SET_ERROR_MSG("client data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  *qos = data->qos;
  return RMW_RET_OK;
}

rmw_ret_t rmw_client_response_subscription_get_actual_qos(
  const rmw_client_t * client,
  rmw_qos_profile_t * qos)
{
  return rmw_client_request_publisher_get_actual_qos(client, qos);
}

rmw_ret_t rmw_service_set_on_new_request_callback(
  rmw_service_t * service,
  rmw_event_callback_t callback,
  const void * user_data)
{
  rmw_ret_t ret = validate_service(service);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxServiceData * data = service_data(service);
  if (data == nullptr) {
    RMW_SET_ERROR_MSG("service data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  size_t pending = 0;
  {
    std::lock_guard<std::mutex> lock(g_service_bus_mutex);
    data->on_new_request_callback = callback;
    data->on_new_request_user_data = user_data;
    pending = data->request_queue.size();
  }
  if (callback != nullptr && pending > 0) {
    callback(user_data, pending);
  }
  return RMW_RET_OK;
}

rmw_ret_t rmw_client_set_on_new_response_callback(
  rmw_client_t * client,
  rmw_event_callback_t callback,
  const void * user_data)
{
  rmw_ret_t ret = validate_client(client);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  FleetQoxServiceData * data = client_data(client);
  if (data == nullptr) {
    RMW_SET_ERROR_MSG("client data is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  size_t pending = 0;
  {
    std::lock_guard<std::mutex> lock(g_service_bus_mutex);
    data->on_new_response_callback = callback;
    data->on_new_response_user_data = user_data;
    pending = data->response_queue.size();
  }
  if (callback != nullptr && pending > 0) {
    callback(user_data, pending);
  }
  return RMW_RET_OK;
}

rmw_ret_t rmw_event_set_callback(
  rmw_event_t * event,
  rmw_event_callback_t callback,
  const void * user_data)
{
  (void)callback;
  (void)user_data;
  if (event == nullptr) {
    RMW_SET_ERROR_MSG("event is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  if (!identifier_matches(event->implementation_identifier)) {
    RMW_SET_ERROR_MSG("event is not from rmw_fleetqox_cpp");
    return RMW_RET_INCORRECT_RMW_IMPLEMENTATION;
  }
  return unsupported("event callbacks are not supported by rmw_fleetqox_cpp yet");
}

bool rmw_feature_supported(rmw_feature_t feature)
{
  (void)feature;
  return false;
}

rmw_ret_t rmw_take_dynamic_message(
  const rmw_subscription_t * subscription,
  rosidl_dynamic_typesupport_dynamic_data_t * dynamic_message,
  bool * taken,
  rmw_subscription_allocation_t * allocation)
{
  (void)dynamic_message;
  (void)allocation;
  rmw_ret_t ret = validate_subscription(subscription);
  if (ret != RMW_RET_OK) {
    return ret;
  }
  if (taken == nullptr) {
    RMW_SET_ERROR_MSG("dynamic message taken output is null");
    return RMW_RET_INVALID_ARGUMENT;
  }
  *taken = false;
  return unsupported("dynamic messages are not supported by rmw_fleetqox_cpp yet");
}

rmw_ret_t rmw_take_dynamic_message_with_info(
  const rmw_subscription_t * subscription,
  rosidl_dynamic_typesupport_dynamic_data_t * dynamic_message,
  bool * taken,
  rmw_message_info_t * message_info,
  rmw_subscription_allocation_t * allocation)
{
  (void)message_info;
  return rmw_take_dynamic_message(subscription, dynamic_message, taken, allocation);
}

rmw_ret_t rmw_serialization_support_init(
  const char * serialization_lib_name,
  rcutils_allocator_t * allocator,
  rosidl_dynamic_typesupport_serialization_support_t * serialization_support)
{
  if (serialization_lib_name == nullptr || allocator == nullptr || serialization_support == nullptr) {
    RMW_SET_ERROR_MSG("serialization support init arguments are invalid");
    return RMW_RET_INVALID_ARGUMENT;
  }
  return unsupported("dynamic serialization support is not supported by rmw_fleetqox_cpp yet");
}

}  // extern "C"
