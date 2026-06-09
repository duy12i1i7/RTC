package fleetqox.omnetpp;

//
// Placeholder simple module for a trace-driven UDP application.
//
// Implement this module in C++ against the installed INET version. It should:
// - read FleetQoX CSV trace rows;
// - emit packets whose source endpoint belongs to this host;
// - attach flow metadata for deadline/utility accounting;
// - record delay, deadline miss, and semantic utility delivered.
//

simple TraceDrivenUdpApp
{
    parameters:
        string traceFile;
        string endpointName;
        int localPort = default(9100);
        int destPort = default(9100);
        @display("i=block/app");
    gates:
        input socketIn;
        output socketOut;
}
