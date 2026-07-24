#include "rmw_fleetqox_cpp/data_frame.hpp"
#include "rmw_fleetqox_cpp/quic_gateway_transport.hpp"

#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace
{

constexpr const char * kTopic = "/fleetqox/nav2_rmf_tasks";
constexpr const char * kPublisher = "nav2-rmf-workload-client";

std::string frame(std::uint64_t sequence)
{
  const std::string text = "nav2-rmf-task-outcome-" + std::to_string(sequence);
  return rmw_fleetqox_cpp::encode_data_frame(
    rmw_fleetqox_cpp::DataFrame{
      "nav2-rmf-workload-robot",
      kTopic,
      kPublisher,
      sequence,
      static_cast<std::int64_t>(sequence * 1000000),
      std::vector<std::uint8_t>(text.begin(), text.end()),
      42,
      "fleetrmw/task/TerminalOutcome",
      "control",
      10000.0,
      0.0,
      0.0,
      1.0,
      false,
      0});
}

bool configure(
  rmw_fleetqox_cpp::QuicGatewayTransport * transport,
  const std::string & path)
{
  if (transport == nullptr) {
    return false;
  }
  const std::string uri = "https://localhost:4511" + path;
  return ::setenv("FLEETQOX_RMW_QUIC_URI", uri.c_str(), 1) == 0 &&
         transport->configure_from_environment();
}

std::vector<std::string> read_documents(const std::string & path)
{
  std::ifstream input(path);
  std::vector<std::string> documents;
  for (std::string line; std::getline(input, line); ) {
    if (!line.empty()) {
      documents.push_back(line);
    }
  }
  return documents;
}

}  // namespace

int main()
{
  const char * document_path = std::getenv("FLEETQOX_TASK_OUTCOME_NDJSON");
  const std::vector<std::string> documents =
    document_path == nullptr ? std::vector<std::string>{} : read_documents(document_path);

  rmw_fleetqox_cpp::QuicGatewayTransport frames;
  const bool frames_configured = configure(&frames, "/fleetrmw/v1/frames");
  std::size_t seeded = 0;
  for (std::uint64_t sequence = 1; frames_configured && sequence <= 3; ++sequence) {
    if (!frames.send(frame(sequence))) {
      break;
    }
    ++seeded;
  }

  rmw_fleetqox_cpp::QuicGatewayTransport outcomes;
  const bool outcomes_configured = seeded == 3 && configure(
    &outcomes, "/fleetrmw/v1/application-outcomes");
  std::size_t submitted = 0;
  for (const std::string & document : documents) {
    if (!outcomes_configured || !outcomes.send(document)) {
      break;
    }
    ++submitted;
  }

  const std::uint64_t connections_created =
    frames.connections_created() + outcomes.connections_created();
  const std::uint64_t handshakes_completed =
    frames.handshakes_completed() + outcomes.handshakes_completed();
  const std::uint64_t streams_opened =
    frames.streams_opened() + outcomes.streams_opened();
  const std::uint64_t connection_reuse_count =
    frames.connection_reuse_count() + outcomes.connection_reuse_count();
  const bool accounting =
    connections_created == 2 && handshakes_completed == 2 &&
    streams_opened == 6 && connection_reuse_count == 4;
  const bool inprocess =
    frames.backend_name() == "inprocess" && outcomes.backend_name() == "inprocess" &&
    !frames.subprocess_backed() && !outcomes.subprocess_backed();
  const bool ok = documents.size() == 3 && seeded == 3 && submitted == 3 &&
    accounting && inprocess;

  if (!ok) {
    std::cerr << "frames_error=" << frames.error() << std::endl;
    std::cerr << "outcomes_error=" << outcomes.error() << std::endl;
  }
  std::cout << "{\"schema_version\":"
    "\"fleetrmw.quic_task_outcome_submit_probe.v1\",";
  std::cout << "\"status\":\"" << (ok ? "ok" : "failed") << "\",";
  std::cout << "\"source_workload_outcome_count\":" << documents.size() << ",";
  std::cout << "\"seed_frames_sent\":" << seeded << ",";
  std::cout << "\"task_outcomes_submitted\":" << submitted << ",";
  std::cout << "\"connections_created\":" << connections_created << ",";
  std::cout << "\"handshakes_completed\":" << handshakes_completed << ",";
  std::cout << "\"streams_opened\":" << streams_opened << ",";
  std::cout << "\"connection_reuse_count\":" << connection_reuse_count << ",";
  std::cout << "\"task_outcome_gateway_submission_performed\":" <<
    (ok ? "true" : "false") << ",";
  std::cout << "\"task_outcome_submission_session_reuse_claim\":" <<
    (ok ? "true" : "false") << ",";
  std::cout << "\"mutual_tls_required\":true,";
  std::cout << "\"subprocess_backed\":false,";
  std::cout << "\"production_readiness\":false}" << std::endl;

  frames.stop();
  outcomes.stop();
  return ok ? 0 : 1;
}
