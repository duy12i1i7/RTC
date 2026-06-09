#include "rmw_fleetqox_cpp/data_frame.hpp"

#include <iostream>
#include <iterator>
#include <sstream>
#include <string>

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

}  // namespace

int main()
{
  const std::string payload{
    std::istreambuf_iterator<char>(std::cin),
    std::istreambuf_iterator<char>()};
  const auto frame = rmw_fleetqox_cpp::decode_data_frame(payload);
  if (!frame) {
    std::cout << "{\"status\":\"ignored\"}" << std::endl;
    return 1;
  }
  std::cout << "{\"status\":\"decoded\",";
  std::cout << "\"robot_id\":\"" << json_escape(frame->robot_id) << "\",";
  std::cout << "\"topic\":\"" << json_escape(frame->topic) << "\",";
  std::cout << "\"publisher_id\":\"" << json_escape(frame->publisher_id) << "\",";
  std::cout << "\"source_sequence_number\":" << frame->source_sequence_number << ",";
  std::cout << "\"source_timestamp_ns\":" << frame->source_timestamp_ns << "}" << std::endl;
  return 0;
}
