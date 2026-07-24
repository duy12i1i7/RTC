#ifndef FLEETQOX_OMNETPP_TRACE_DRIVEN_UDP_APP_H
#define FLEETQOX_OMNETPP_TRACE_DRIVEN_UDP_APP_H

#include <cstddef>
#include <string>
#include <vector>

#include <omnetpp.h>

#include "inet/transportlayer/contract/udp/UdpSocket.h"

namespace fleetqox_omnetpp {

class TraceDrivenUdpApp final : public ::omnetpp::cSimpleModule,
                                public inet::UdpSocket::ICallback
{
public:
  TraceDrivenUdpApp() = default;
  ~TraceDrivenUdpApp() override;

protected:
  int numInitStages() const override;
  void initialize(int stage) override;
  void handleMessage(::omnetpp::cMessage * message) override;
  void finish() override;

  void socketDataArrived(inet::UdpSocket * socket, inet::Packet * packet) override;
  void socketErrorArrived(inet::UdpSocket * socket, inet::Indication * indication) override;
  void socketClosed(inet::UdpSocket * socket) override;

private:
  void scheduleNextEvent();
  void sendDueEvents();

  inet::UdpSocket socket_;
  ::omnetpp::cMessage * send_timer_{nullptr};
  std::string endpoint_name_;
  std::vector<std::size_t> outgoing_events_;
  std::size_t next_outgoing_event_{0};
  int local_port_{9100};
  int destination_port_{9100};
  double start_offset_ms_{0.0};
  bool summary_writer_{false};
  std::uint64_t sent_{0};
  std::uint64_t received_{0};
};

}  // namespace fleetqox_omnetpp

#endif  // FLEETQOX_OMNETPP_TRACE_DRIVEN_UDP_APP_H
