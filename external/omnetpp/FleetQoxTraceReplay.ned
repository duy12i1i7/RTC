package fleetqox.omnetpp;

//
// Starter NED topology for FleetQoX trace replay.
//
// This is a template to be validated against the installed INET version. The
// first concrete integration should implement TraceDrivenUdpApp.cc and map the
// CSV trace to UDP packets and traffic classes.
//

import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.node.inet.StandardHost;
import inet.node.ethernet.EthernetSwitch;

network FleetQoxTraceReplay
{
    parameters:
        int numRobots = default(100);
        @display("bgb=900,600");
    submodules:
        configurator: Ipv4NetworkConfigurator {
            @display("p=80,60");
        }
        fleetRouter: StandardHost {
            @display("p=450,80");
        }
        operatorUi: StandardHost {
            @display("p=650,80");
        }
        controller: StandardHost {
            @display("p=250,80");
        }
        switch: EthernetSwitch {
            @display("p=450,260");
        }
        robot[numRobots]: StandardHost {
            @display("p=100+index*7,480");
        }
}
