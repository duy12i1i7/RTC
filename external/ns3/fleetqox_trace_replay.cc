// FleetQoX trace replay starter for ns-3.
//
// Copy this file into an ns-3 workspace under scratch/ and run it with:
//
//   ./ns3 run "scratch/fleetqox_trace_replay --trace=/path/to/trace.csv"
//
// The topology is intentionally simple: all endpoints are attached to a shared
// CSMA channel. The goal is to validate trace import, per-flow delay, deadline
// miss, and utility accounting before introducing Wi-Fi/5G/mesh models.

#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/csma-module.h"
#include "ns3/internet-module.h"
#include "ns3/network-module.h"

#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("FleetQoxTraceReplay");

class EventIdTag : public Tag
{
public:
  EventIdTag() = default;
  explicit EventIdTag(uint32_t id) : m_id(id) {}

  static TypeId GetTypeId()
  {
    static TypeId tid = TypeId("EventIdTag")
                            .SetParent<Tag>()
                            .AddConstructor<EventIdTag>();
    return tid;
  }

  TypeId GetInstanceTypeId() const override { return GetTypeId(); }
  uint32_t GetSerializedSize() const override { return 4; }
  void Serialize(TagBuffer i) const override { i.WriteU32(m_id); }
  void Deserialize(TagBuffer i) override { m_id = i.ReadU32(); }
  void Print(std::ostream& os) const override { os << m_id; }
  uint32_t Get() const { return m_id; }

private:
  uint32_t m_id = 0;
};

struct TraceEvent
{
  uint32_t id = 0;
  double timestampMs = 0.0;
  std::string policy;
  std::string flowId;
  std::string flowClass;
  std::string src;
  std::string dst;
  uint32_t bytes = 0;
  double deadlineMs = 0.0;
  double utility = 0.0;
};

struct PolicyStats
{
  uint64_t tx = 0;
  uint64_t rx = 0;
  uint64_t bytes = 0;
  uint64_t deadlineMiss = 0;
  double utilityDelivered = 0.0;
  std::vector<double> latencyMs;
};

static std::vector<TraceEvent> g_events;
static std::map<std::string, uint32_t> g_endpointToNode;
static std::map<uint32_t, Ipv4Address> g_nodeToAddress;
static std::map<std::string, Ptr<Socket>> g_sourceSockets;
static std::map<std::string, PolicyStats> g_stats;
static uint16_t g_port = 9100;

static std::vector<std::string>
SplitCsvLine(const std::string& line)
{
  std::vector<std::string> out;
  std::stringstream ss(line);
  std::string cell;
  while (std::getline(ss, cell, ','))
  {
    out.push_back(cell);
  }
  return out;
}

static uint32_t
Column(const std::vector<std::string>& header, const std::string& name)
{
  auto it = std::find(header.begin(), header.end(), name);
  if (it == header.end())
  {
    NS_FATAL_ERROR("missing CSV column: " << name);
  }
  return static_cast<uint32_t>(std::distance(header.begin(), it));
}

static double
ToDouble(const std::string& value)
{
  return std::stod(value);
}

static uint32_t
ToUint(const std::string& value)
{
  return static_cast<uint32_t>(std::stoul(value));
}

static std::vector<TraceEvent>
LoadTrace(const std::string& path)
{
  std::ifstream input(path);
  if (!input)
  {
    NS_FATAL_ERROR("could not open trace: " << path);
  }

  std::string headerLine;
  std::getline(input, headerLine);
  auto header = SplitCsvLine(headerLine);

  const auto eventId = Column(header, "event_id");
  const auto timestamp = Column(header, "timestamp_ms");
  const auto policy = Column(header, "policy");
  const auto flowId = Column(header, "flow_id");
  const auto flowClass = Column(header, "flow_class");
  const auto src = Column(header, "src");
  const auto dst = Column(header, "dst");
  const auto bytes = Column(header, "bytes");
  const auto deadline = Column(header, "deadline_ms");
  const auto utility = Column(header, "semantic_utility");

  std::vector<TraceEvent> events;
  std::string line;
  while (std::getline(input, line))
  {
    if (line.empty())
    {
      continue;
    }
    auto row = SplitCsvLine(line);
    TraceEvent event;
    event.id = ToUint(row[eventId]);
    event.timestampMs = ToDouble(row[timestamp]);
    event.policy = row[policy];
    event.flowId = row[flowId];
    event.flowClass = row[flowClass];
    event.src = row[src];
    event.dst = row[dst];
    event.bytes = ToUint(row[bytes]);
    event.deadlineMs = ToDouble(row[deadline]);
    event.utility = ToDouble(row[utility]);
    events.push_back(event);
  }

  return events;
}

static void
ReceivePacket(Ptr<Socket> socket)
{
  Ptr<Packet> packet;
  Address from;
  while ((packet = socket->RecvFrom(from)))
  {
    EventIdTag tag;
    if (!packet->PeekPacketTag(tag))
    {
      continue;
    }
    const uint32_t id = tag.Get();
    if (id >= g_events.size())
    {
      continue;
    }
    const TraceEvent& event = g_events[id];
    auto& stats = g_stats[event.policy];
    stats.rx++;
    stats.bytes += packet->GetSize();

    const double latencyMs = Simulator::Now().GetMilliSeconds() - event.timestampMs;
    stats.latencyMs.push_back(latencyMs);
    if (latencyMs > event.deadlineMs)
    {
      stats.deadlineMiss++;
    }
    stats.utilityDelivered += event.utility;
  }
}

static Ptr<Socket>
SourceSocket(const std::string& src, Ptr<Node> node)
{
  auto it = g_sourceSockets.find(src);
  if (it != g_sourceSockets.end())
  {
    return it->second;
  }
  Ptr<Socket> socket = Socket::CreateSocket(node, UdpSocketFactory::GetTypeId());
  g_sourceSockets[src] = socket;
  return socket;
}

static void
SendEvent(uint32_t eventIndex, NodeContainer nodes)
{
  const TraceEvent& event = g_events[eventIndex];
  Ptr<Node> srcNode = nodes.Get(g_endpointToNode[event.src]);
  Ptr<Socket> socket = SourceSocket(event.src, srcNode);
  const Ipv4Address dstAddress = g_nodeToAddress[g_endpointToNode[event.dst]];

  Ptr<Packet> packet = Create<Packet>(std::max<uint32_t>(event.bytes, 1));
  packet->AddPacketTag(EventIdTag(eventIndex));
  socket->SendTo(packet, 0, InetSocketAddress(dstAddress, g_port));
  g_stats[event.policy].tx++;
}

static double
Percentile(std::vector<double> values, double pct)
{
  if (values.empty())
  {
    return 0.0;
  }
  std::sort(values.begin(), values.end());
  const auto index = static_cast<size_t>(
      std::min<double>(values.size() - 1, std::ceil((pct / 100.0) * values.size()) - 1));
  return values[index];
}

static void
PrintSummary()
{
  std::cout << "policy,tx,rx,bytes,deadline_miss_ratio,p50_ms,p99_ms,utility\n";
  for (auto& [policy, stats] : g_stats)
  {
    const double missRatio = stats.rx == 0 ? 0.0 : static_cast<double>(stats.deadlineMiss) / stats.rx;
    std::cout << policy << "," << stats.tx << "," << stats.rx << "," << stats.bytes << ","
              << missRatio << "," << Percentile(stats.latencyMs, 50.0) << ","
              << Percentile(stats.latencyMs, 99.0) << "," << stats.utilityDelivered << "\n";
  }
}

int
main(int argc, char* argv[])
{
  std::string tracePath;
  std::string dataRate = "54Mbps";
  std::string delay = "2ms";

  CommandLine cmd(__FILE__);
  cmd.AddValue("trace", "FleetQoX simulator CSV trace", tracePath);
  cmd.AddValue("dataRate", "CSMA data rate", dataRate);
  cmd.AddValue("delay", "CSMA channel delay", delay);
  cmd.Parse(argc, argv);

  if (tracePath.empty())
  {
    NS_FATAL_ERROR("missing --trace=/path/to/trace.csv");
  }

  g_events = LoadTrace(tracePath);
  for (const auto& event : g_events)
  {
    if (!g_endpointToNode.count(event.src))
    {
      g_endpointToNode[event.src] = static_cast<uint32_t>(g_endpointToNode.size());
    }
    if (!g_endpointToNode.count(event.dst))
    {
      g_endpointToNode[event.dst] = static_cast<uint32_t>(g_endpointToNode.size());
    }
  }

  NodeContainer nodes;
  nodes.Create(g_endpointToNode.size());

  CsmaHelper csma;
  csma.SetChannelAttribute("DataRate", StringValue(dataRate));
  csma.SetChannelAttribute("Delay", StringValue(delay));
  NetDeviceContainer devices = csma.Install(nodes);

  InternetStackHelper internet;
  internet.Install(nodes);

  Ipv4AddressHelper ipv4;
  ipv4.SetBase("10.10.0.0", "255.255.0.0");
  Ipv4InterfaceContainer interfaces = ipv4.Assign(devices);

  for (const auto& [endpoint, nodeIndex] : g_endpointToNode)
  {
    g_nodeToAddress[nodeIndex] = interfaces.GetAddress(nodeIndex);
    Ptr<Socket> sink = Socket::CreateSocket(nodes.Get(nodeIndex), UdpSocketFactory::GetTypeId());
    sink->Bind(InetSocketAddress(Ipv4Address::GetAny(), g_port));
    sink->SetRecvCallback(MakeCallback(&ReceivePacket));
  }

  for (uint32_t i = 0; i < g_events.size(); ++i)
  {
    Simulator::Schedule(MilliSeconds(g_events[i].timestampMs), &SendEvent, i, nodes);
  }

  const double stopMs = g_events.empty() ? 0.0 : g_events.back().timestampMs + 10'000.0;
  Simulator::Stop(MilliSeconds(stopMs));
  Simulator::Run();
  PrintSummary();
  Simulator::Destroy();
  return 0;
}
