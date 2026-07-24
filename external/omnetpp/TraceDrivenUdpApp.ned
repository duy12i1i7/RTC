package fleetqox.omnetpp;

import inet.applications.contract.IApp;
import inet.common.SimpleModule;

// Replays rows whose src column matches endpointName and receives UDP packets
// addressed to the endpoint. The C++ module records the same policy summary
// columns emitted by external/ns3/fleetqox_trace_replay.cc.
simple TraceDrivenUdpApp extends SimpleModule like IApp
{
    parameters:
        @class(fleetqox_omnetpp::TraceDrivenUdpApp);
        string traceFile;
        string endpointName;
        int localPort = default(9100);
        int destPort = default(9100);
        double startOffset @unit(s) = default(100ms);
        bool summaryWriter = default(false);
        @display("i=block/app");
    gates:
        input socketIn @labels(UdpCommand/up);
        output socketOut @labels(UdpCommand/down);
}
