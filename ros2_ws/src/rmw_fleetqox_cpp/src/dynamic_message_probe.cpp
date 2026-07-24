#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <thread>

#include "rcutils/allocator.h"
#include "rmw/dynamic_message_type_support.h"
#include "rmw/init.h"
#include "rmw/init_options.h"
#include "rmw/publisher_options.h"
#include "rmw/qos_profiles.h"
#include "rmw/rmw.h"
#include "rmw/serialized_message.h"
#include "rmw/subscription_options.h"
#include "rosidl_dynamic_typesupport/api/dynamic_data.h"
#include "rosidl_dynamic_typesupport/api/dynamic_type.h"
#include "rosidl_dynamic_typesupport/api/serialization_support.h"
#include "rosidl_runtime_c/message_type_support_struct.h"

namespace
{

constexpr const char * kSchema = "fleetrmw.dynamic_message_probe.v1";
constexpr const char * kPayload = "fleetqox-dynamic-string";

bool wait_dynamic_take(
  const rmw_subscription_t * subscription,
  rosidl_dynamic_typesupport_dynamic_data_t * dynamic_data,
  bool with_info,
  bool * taken,
  bool * message_info_ok = nullptr)
{
  *taken = false;
  if (message_info_ok != nullptr) {
    *message_info_ok = false;
  }
  for (int attempt = 0; attempt < 300 && !*taken; ++attempt) {
    rmw_ret_t ret = RMW_RET_ERROR;
    if (with_info) {
      rmw_message_info_t info{};
      ret = rmw_take_dynamic_message_with_info(
        subscription, dynamic_data, taken, &info, nullptr);
      if (ret == RMW_RET_OK && *taken && message_info_ok != nullptr) {
        *message_info_ok = info.source_timestamp > 0 &&
          info.received_timestamp >= info.source_timestamp &&
          info.publication_sequence_number > 0 &&
          info.reception_sequence_number > 0 &&
          info.publisher_gid.implementation_identifier != nullptr;
      }
    } else {
      ret = rmw_take_dynamic_message(
        subscription, dynamic_data, taken, nullptr);
    }
    if (ret != RMW_RET_OK) {
      return false;
    }
    if (!*taken) {
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  }
  return true;
}

}  // namespace

int main()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  rosidl_dynamic_typesupport_serialization_support_t serialization_support =
    rosidl_dynamic_typesupport_get_zero_initialized_serialization_support();
  const rmw_ret_t serialization_init_ret = rmw_serialization_support_init(
    "rosidl_dynamic_typesupport_fastrtps", &allocator, &serialization_support);
  if (serialization_init_ret != RMW_RET_OK) {
    std::cout << "{\"schema_version\":\"" << kSchema <<
      "\",\"status\":\"serialization_support_init_failed\"}" << std::endl;
    return 1;
  }

  rosidl_dynamic_typesupport_dynamic_type_builder_t builder =
    rosidl_dynamic_typesupport_get_zero_initialized_dynamic_type_builder();
  rosidl_dynamic_typesupport_dynamic_type_t dynamic_type =
    rosidl_dynamic_typesupport_get_zero_initialized_dynamic_type();
  rosidl_dynamic_typesupport_dynamic_data_t outgoing_dynamic =
    rosidl_dynamic_typesupport_get_zero_initialized_dynamic_data();
  rosidl_dynamic_typesupport_dynamic_data_t incoming_dynamic =
    rosidl_dynamic_typesupport_get_zero_initialized_dynamic_data();
  constexpr const char * kDynamicTypeName = "fleetqox::DynamicString";
  const bool dynamic_objects_ok =
    rosidl_dynamic_typesupport_dynamic_type_builder_init(
      &serialization_support, kDynamicTypeName, std::strlen(kDynamicTypeName),
      &allocator, &builder) == RCUTILS_RET_OK &&
    rosidl_dynamic_typesupport_dynamic_type_builder_add_string_member(
      &builder, 0, "data", 4, "", 0) == RCUTILS_RET_OK &&
    rosidl_dynamic_typesupport_dynamic_type_init_from_dynamic_type_builder(
      &builder, &allocator, &dynamic_type) == RCUTILS_RET_OK &&
    rosidl_dynamic_typesupport_dynamic_data_init_from_dynamic_type(
      &dynamic_type, &allocator, &outgoing_dynamic) == RCUTILS_RET_OK &&
    rosidl_dynamic_typesupport_dynamic_data_init_from_dynamic_type(
      &dynamic_type, &allocator, &incoming_dynamic) == RCUTILS_RET_OK &&
    rosidl_dynamic_typesupport_dynamic_data_set_string_value(
      &outgoing_dynamic, 0, kPayload, std::strlen(kPayload)) == RCUTILS_RET_OK;
  if (!dynamic_objects_ok) {
    std::cout << "{\"schema_version\":\"" << kSchema <<
      "\",\"status\":\"dynamic_object_init_failed\"}" << std::endl;
    return 1;
  }

  rmw_serialized_message_t outgoing = rmw_get_zero_initialized_serialized_message();
  if (rmw_serialized_message_init(&outgoing, 0, &allocator) != RMW_RET_OK ||
    rosidl_dynamic_typesupport_dynamic_data_serialize(
      &outgoing_dynamic, &outgoing) != RCUTILS_RET_OK)
  {
    std::cout << "{\"schema_version\":\"" << kSchema <<
      "\",\"status\":\"dynamic_serialize_failed\"}" << std::endl;
    return 1;
  }

  rmw_init_options_t options = rmw_get_zero_initialized_init_options();
  rmw_context_t context = rmw_get_zero_initialized_context();
  if (rmw_init_options_init(&options, allocator) != RMW_RET_OK ||
    rmw_init(&options, &context) != RMW_RET_OK)
  {
    std::cout << "{\"schema_version\":\"" << kSchema <<
      "\",\"status\":\"rmw_init_failed\"}" << std::endl;
    return 1;
  }
  rmw_node_t * node = rmw_create_node(&context, "dynamic_message_probe", "/fleetqox");
  rosidl_message_type_support_t type_support{};
  type_support.typesupport_identifier = "rmw_fleetqox_cpp_dynamic_probe";
  rmw_qos_profile_t qos = rmw_qos_profile_default;
  rmw_publisher_options_t publisher_options = rmw_get_default_publisher_options();
  rmw_subscription_options_t subscription_options = rmw_get_default_subscription_options();
  rmw_publisher_t * publisher = node == nullptr ? nullptr : rmw_create_publisher(
    node, &type_support, "/fleetqox/dynamic_message", &qos, &publisher_options);
  rmw_subscription_t * subscription = node == nullptr ? nullptr : rmw_create_subscription(
    node, &type_support, "/fleetqox/dynamic_message", &qos, &subscription_options);
  if (node == nullptr || publisher == nullptr || subscription == nullptr) {
    std::cout << "{\"schema_version\":\"" << kSchema <<
      "\",\"status\":\"endpoint_init_failed\"}" << std::endl;
    return 1;
  }

  const rmw_ret_t publish_ret = rmw_publish_serialized_message(
    publisher, &outgoing, nullptr);
  bool taken = false;
  const bool take_ok = wait_dynamic_take(
    subscription, &incoming_dynamic, false, &taken);
  char * value = nullptr;
  size_t value_size = 0;
  const bool value_ok = taken &&
    rosidl_dynamic_typesupport_dynamic_data_get_string_value(
      &incoming_dynamic, 0, &value, &value_size) == RCUTILS_RET_OK &&
    value != nullptr && std::string(value, value_size) == kPayload;
  if (value != nullptr) {
    allocator.deallocate(value, allocator.state);
  }

  const rmw_ret_t second_publish_ret = rmw_publish_serialized_message(
    publisher, &outgoing, nullptr);
  bool taken_with_info = false;
  bool message_info_ok = false;
  const bool take_with_info_ok = wait_dynamic_take(
    subscription, &incoming_dynamic, true, &taken_with_info, &message_info_ok);
  const bool ok = publish_ret == RMW_RET_OK && second_publish_ret == RMW_RET_OK &&
    take_ok && taken && value_ok && take_with_info_ok && taken_with_info && message_info_ok &&
    rmw_feature_supported(RMW_MIDDLEWARE_CAN_TAKE_DYNAMIC_MESSAGE) &&
    rmw_feature_supported(RMW_FEATURE_MESSAGE_INFO_PUBLICATION_SEQUENCE_NUMBER) &&
    rmw_feature_supported(RMW_FEATURE_MESSAGE_INFO_RECEPTION_SEQUENCE_NUMBER);

  std::cout << "{\"schema_version\":\"" << kSchema << "\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"serialization_library\":\"rosidl_dynamic_typesupport_fastrtps\",";
  std::cout << "\"serialized_bytes\":" << outgoing.buffer_length << ",";
  std::cout << "\"taken\":" << (taken ? "true" : "false") << ",";
  std::cout << "\"value_ok\":" << (value_ok ? "true" : "false") << ",";
  std::cout << "\"taken_with_info\":" << (taken_with_info ? "true" : "false") << ",";
  std::cout << "\"message_info_ok\":" << (message_info_ok ? "true" : "false") << ",";
  std::cout << "\"dynamic_take_feature_reported\":" <<
    (rmw_feature_supported(RMW_MIDDLEWARE_CAN_TAKE_DYNAMIC_MESSAGE) ? "true" : "false") << ",";
  std::cout << "\"message_info_sequence_features_reported\":" <<
    (rmw_feature_supported(RMW_FEATURE_MESSAGE_INFO_PUBLICATION_SEQUENCE_NUMBER) &&
    rmw_feature_supported(RMW_FEATURE_MESSAGE_INFO_RECEPTION_SEQUENCE_NUMBER) ?
    "true" : "false") << ",";
  std::cout << "\"dynamic_serialization_support_claim\":" <<
    (serialization_init_ret == RMW_RET_OK ? "true" : "false") << ",";
  std::cout << "\"dynamic_message_take_claim\":" << (ok ? "true" : "false") <<
    "}" << std::endl;

  const rmw_ret_t destroy_publisher_ret = rmw_destroy_publisher(node, publisher);
  const rmw_ret_t destroy_subscription_ret = rmw_destroy_subscription(node, subscription);
  const rmw_ret_t destroy_node_ret = rmw_destroy_node(node);
  const rmw_ret_t shutdown_ret = rmw_shutdown(&context);
  const rmw_ret_t context_fini_ret = rmw_context_fini(&context);
  const rmw_ret_t options_fini_ret = rmw_init_options_fini(&options);
  const rmw_ret_t serialized_fini_ret = rmw_serialized_message_fini(&outgoing);
  const rcutils_ret_t incoming_fini_ret =
    rosidl_dynamic_typesupport_dynamic_data_fini(&incoming_dynamic);
  const rcutils_ret_t outgoing_fini_ret =
    rosidl_dynamic_typesupport_dynamic_data_fini(&outgoing_dynamic);
  const rcutils_ret_t type_fini_ret =
    rosidl_dynamic_typesupport_dynamic_type_fini(&dynamic_type);
  const rcutils_ret_t builder_fini_ret =
    rosidl_dynamic_typesupport_dynamic_type_builder_fini(&builder);
  const rcutils_ret_t support_fini_ret =
    rosidl_dynamic_typesupport_serialization_support_fini(&serialization_support);
  const bool cleanup_ok = destroy_publisher_ret == RMW_RET_OK &&
    destroy_subscription_ret == RMW_RET_OK && destroy_node_ret == RMW_RET_OK &&
    shutdown_ret == RMW_RET_OK && context_fini_ret == RMW_RET_OK &&
    options_fini_ret == RMW_RET_OK && serialized_fini_ret == RMW_RET_OK &&
    incoming_fini_ret == RCUTILS_RET_OK && outgoing_fini_ret == RCUTILS_RET_OK &&
    type_fini_ret == RCUTILS_RET_OK && builder_fini_ret == RCUTILS_RET_OK &&
    support_fini_ret == RCUTILS_RET_OK;
  return ok && cleanup_ok ? 0 : 1;
}
