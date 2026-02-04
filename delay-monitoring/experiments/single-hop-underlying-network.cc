// Single Hop Network 
//
//       10.1.1.0
// n0 -------------- n1
//    point-to-point
//

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "variable-delay-application.h"

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("SingleHop");

int
main(int argc, char* argv[])
{
    // set up and defaults 

    std::string delayDist = "lognormal";
    
    double lognormal_mu = 2.3;
    double lognormal_sigma = 0.2;
    
    double weibull_scale = 10.0;
    double weibull_shape = 2.0;
    
    double normal_mean = 10.0;
    double normal_variance = 4.0;
    
    uint32_t numPackets = 100;
    
    CommandLine cmd(__FILE__);
    cmd.AddValue("delayDist", "Delay distribution: lognormal, weibull, normal", delayDist);
    cmd.AddValue("lognormal_mu", "LogNormal Mu parameter", lognormal_mu);
    cmd.AddValue("lognormal_sigma", "LogNormal Sigma parameter", lognormal_sigma);
    cmd.AddValue("weibull_scale", "Weibull scale parameter", weibull_scale);
    cmd.AddValue("weibull_shape", "Weibull shape parameter", weibull_shape);
    cmd.AddValue("normal_mean", "Normal mean parameter", normal_mean);
    cmd.AddValue("normal_variance", "Normal variance parameter", normal_variance);
    cmd.AddValue("numPackets", "Number of packets to send", numPackets);
    cmd.Parse(argc, argv);

    Time::SetResolution(Time::NS);
    LogComponentEnable("SingleHop", LOG_LEVEL_INFO);
    LogComponentEnable("VariableDelayApplication", LOG_LEVEL_INFO);

    NS_LOG_INFO("=== Two-Node Network: " << delayDist << ", " << numPackets << " packets ===");

    // set up the simple network topology

    NodeContainer nodes;
    nodes.Create(2);

    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate", StringValue("10Mbps"));

    NetDeviceContainer devices = p2p.Install(nodes);

    InternetStackHelper stack;
    stack.Install(nodes);

    Ipv4AddressHelper address;
    address.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer interfaces = address.Assign(devices);

    // configure delay distribution 
    Ptr<RandomVariableStream> delayRv;
    
    if (delayDist == "lognormal") { 
        Ptr<LogNormalRandomVariable> lnrv = CreateObject<LogNormalRandomVariable>();
        lnrv->SetAttribute("Mu", DoubleValue(lognormal_mu));
        lnrv->SetAttribute("Sigma", DoubleValue(lognormal_sigma));
        delayRv = lnrv;
        NS_LOG_INFO("LogNormal: Mu=" << lognormal_mu << ", Sigma=" << lognormal_sigma);
    }
    else if (delayDist == "weibull") {
        Ptr<WeibullRandomVariable> wrv = CreateObject<WeibullRandomVariable>();
        wrv->SetAttribute("Scale", DoubleValue(weibull_scale));
        wrv->SetAttribute("Shape", DoubleValue(weibull_shape));
        delayRv = wrv;
        NS_LOG_INFO("Weibull: Scale=" << weibull_scale << ", Shape=" << weibull_shape);
    }
    else if (delayDist == "normal") {
        Ptr<NormalRandomVariable> nrv = CreateObject<NormalRandomVariable>();
        nrv->SetAttribute("Mean", DoubleValue(normal_mean));
        nrv->SetAttribute("Variance", DoubleValue(normal_variance));
        delayRv = nrv;
        NS_LOG_INFO("Normal: Mean=" << normal_mean << ", Variance=" << normal_variance);
    }
    else {
        NS_FATAL_ERROR("Unknown distribution: " << delayDist);
    }

    uint16_t port = 9;
    
    // receiver on egress node
    Ptr<VariableDelayReceiver> receiver = CreateObject<VariableDelayReceiver>();
    receiver->SetPort(port);
    nodes.Get(1)->AddApplication(receiver);
    receiver->SetStartTime(Seconds(1.0));
    receiver->SetStopTime(Seconds(100.0));

    // sender on ingress node after sampling from dist
    Ptr<VariableDelaySender> sender = CreateObject<VariableDelaySender>();
    sender->SetRemote(interfaces.GetAddress(1), port);
    sender->SetDelayRandomVariable(delayRv);
    sender->SetPacketSize(1024);
    sender->SetMaxPackets(numPackets);
    sender->SetInterval(MilliSeconds(100));
    nodes.Get(0)->AddApplication(sender);
    sender->SetStartTime(Seconds(2.0));
    sender->SetStopTime(Seconds(100.0));

    // run and clean up

    Simulator::Run();
    NS_LOG_INFO("Simulation complete. Packets received: " << receiver->GetReceived());
    Simulator::Destroy();
    
    return 0;
}