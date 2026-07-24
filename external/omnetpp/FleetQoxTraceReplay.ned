package fleetqox.omnetpp;

import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.node.inet.Router;
import inet.node.inet.StandardHost;
import ned.DatarateChannel;

// A full-duplex point-to-point access link. The parity runner converts each
// end-to-end delay/PER target into two identical endpoint-to-router links.
channel FleetQoxPointToPointLink extends DatarateChannel
{
    datarate = default(54Mbps);
    delay = default(1ms);
    per = default(0);
}

// Every FleetQoX trace endpoint is represented by an INET StandardHost. The
// transit Router and two-link PPP path match the ns-3 p2p_star topology.
// TraceDrivenUdpApp performs actual UDP sends and receive accounting.
network FleetQoxTraceReplay
{
    parameters:
        int numRobots = default(8);
        string traceFile;
        double linkDataRate @unit(bps) = default(54Mbps);
        double linkDelay @unit(s) = default(1ms);
        double linkPacketErrorRate = default(0);
        double startOffset @unit(s) = default(100ms);
        @display("bgb=1000,650");
    submodules:
        configurator: Ipv4NetworkConfigurator {
            @display("p=80,60");
        }
        controller: StandardHost {
            parameters:
                numApps = 1;
                app[0].typename = "fleetqox.omnetpp.TraceDrivenUdpApp";
                app[0].traceFile = parent.traceFile;
                app[0].endpointName = "fleet_controller";
                app[0].startOffset = parent.startOffset;
                app[0].summaryWriter = true;
                @display("p=250,100");
        }
        fleetRouter: StandardHost {
            parameters:
                numApps = 1;
                app[0].typename = "fleetqox.omnetpp.TraceDrivenUdpApp";
                app[0].traceFile = parent.traceFile;
                app[0].endpointName = "fleet_router";
                app[0].startOffset = parent.startOffset;
                @display("p=500,100");
        }
        operatorUi: StandardHost {
            parameters:
                numApps = 1;
                app[0].typename = "fleetqox.omnetpp.TraceDrivenUdpApp";
                app[0].traceFile = parent.traceFile;
                app[0].endpointName = "operator_ui";
                app[0].startOffset = parent.startOffset;
                @display("p=750,100");
        }
        backboneRouter: Router {
            @display("p=500,300");
        }
        robot[numRobots]: StandardHost {
            parameters:
                numApps = 1;
                app[0].typename = "fleetqox.omnetpp.TraceDrivenUdpApp";
                app[0].traceFile = parent.traceFile;
                app[0].endpointName = "";
                app[0].startOffset = parent.startOffset;
                @display("p=70+index*105,520");
        }
    connections:
        controller.pppg++ <--> FleetQoxPointToPointLink {
            datarate = parent.linkDataRate;
            delay = parent.linkDelay;
            per = parent.linkPacketErrorRate;
        } <--> backboneRouter.pppg++;
        fleetRouter.pppg++ <--> FleetQoxPointToPointLink {
            datarate = parent.linkDataRate;
            delay = parent.linkDelay;
            per = parent.linkPacketErrorRate;
        } <--> backboneRouter.pppg++;
        operatorUi.pppg++ <--> FleetQoxPointToPointLink {
            datarate = parent.linkDataRate;
            delay = parent.linkDelay;
            per = parent.linkPacketErrorRate;
        } <--> backboneRouter.pppg++;
        for i=0..numRobots-1 {
            robot[i].pppg++ <--> FleetQoxPointToPointLink {
                datarate = parent.linkDataRate;
                delay = parent.linkDelay;
                per = parent.linkPacketErrorRate;
            } <--> backboneRouter.pppg++;
        }
}
