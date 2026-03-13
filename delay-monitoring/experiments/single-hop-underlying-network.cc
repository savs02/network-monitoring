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
#include "delay-monitor.h"
// BinomialRandomVariable is built into NS-3 core (random-variable-stream.h)

// binning monitor kept for reference but not used in this experiment
// #include "binning-monitor.h"
// DoubleTimeBinMonitor* g_ingressMonitor = nullptr;
// DoubleTimeBinMonitor* g_egressMonitor = nullptr;
// void PacketDeparture(Ptr<const Packet> packet, const Address& address)
// {
//     if (g_ingressMonitor) g_ingressMonitor->RecordPacket(Simulator::Now());
// }
// void PacketArrival(Ptr<const Packet> packet, const Address& address)
// {
//     if (g_egressMonitor) g_egressMonitor->RecordPacket(Simulator::Now());
// }

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("SingleHop");

int
main(int argc, char* argv[])
{
    // set up and defaults 

    std::string delayDist = "normal";
    
    double lognormal_mu = 2.3;
    double lognormal_sigma = 0.2;
    
    double weibull_scale = 10.0;
    double weibull_shape = 2.0;

    double normal_mean = 40.0;
    double normal_variance = 4.0;

    // binomial distribution parameters
    uint32_t binomial_trials = 20;
    double   binomial_prob   = 0.5; // mean delay = trials * prob ms
    
    uint32_t numPackets = 100;

    // interval distribution parameters
    double intervalMean = 1.0; // mean inter-packet time in ms (exponential)

    // output file for delay samples (default uses distribution name)
    std::string outputFile = "";

    // binning monitor parameters (kept for reference, not used)
    // bool enableMonitoring = false;
    // double binWidth = 5.0;
    
    CommandLine cmd(__FILE__);
    cmd.AddValue("delayDist", "Delay distribution: lognormal, weibull, normal", delayDist);
    cmd.AddValue("lognormal_mu", "LogNormal Mu parameter", lognormal_mu);
    cmd.AddValue("lognormal_sigma", "LogNormal Sigma parameter", lognormal_sigma);
    cmd.AddValue("weibull_scale", "Weibull scale parameter", weibull_scale);
    cmd.AddValue("weibull_shape", "Weibull shape parameter", weibull_shape);
    cmd.AddValue("normal_mean", "Normal mean parameter", normal_mean);
    cmd.AddValue("normal_variance", "Normal variance parameter", normal_variance);
    cmd.AddValue("binomial_trials", "Binomial number of trials (N)", binomial_trials);
    cmd.AddValue("binomial_prob", "Binomial success probability (p)", binomial_prob);
    cmd.AddValue("numPackets", "Number of packets to send", numPackets);
    cmd.AddValue("intervalMean", "Mean inter-packet interval in ms (exponential)", intervalMean);
    cmd.AddValue("outputFile", "Output CSV path for delay samples (default: results/delay_samples_{dist}.csv)", outputFile);
    // cmd.AddValue("enableMonitoring", "Enable binning monitoring", enableMonitoring);
    // cmd.AddValue("binWidth", "Bin width in ms", binWidth);
    cmd.Parse(argc, argv);

    Time::SetResolution(Time::NS);
    LogComponentEnable("SingleHop", LOG_LEVEL_INFO);
    LogComponentEnable("VariableDelayApplication", LOG_LEVEL_INFO);

    NS_LOG_INFO("=== Two-Node Network: " << delayDist << ", " << numPackets << " packets ===");
    NS_LOG_INFO("Inter-packet interval: Exponential with mean " << intervalMean << "ms");

    // baseline delay monitor: records each sampled delay directly from the sender
    DelayMonitor delayMonitor;

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
    else if (delayDist == "binomial") {
        Ptr<BinomialRandomVariable> brv = CreateObject<BinomialRandomVariable>();
        brv->SetAttribute("Trials", IntegerValue(binomial_trials));
        brv->SetAttribute("Probability", DoubleValue(binomial_prob));
        delayRv = brv;
        NS_LOG_INFO("Binomial: Trials=" << binomial_trials << ", Prob=" << binomial_prob
                    << " (mean=" << binomial_trials * binomial_prob << "ms)");
    }
    else {
        NS_FATAL_ERROR("Unknown distribution: " << delayDist);
    }

    // configure interval distribution (exponential for Poisson arrivals)
    Ptr<ExponentialRandomVariable> intervalRv = CreateObject<ExponentialRandomVariable>();
    intervalRv->SetAttribute("Mean", DoubleValue(intervalMean));

    uint16_t port = 9;
    
    // receiver on egress node
    Ptr<VariableDelayReceiver> receiver = CreateObject<VariableDelayReceiver>();
    receiver->SetPort(port);
    nodes.Get(1)->AddApplication(receiver);
    receiver->SetStartTime(Seconds(0.0));
    receiver->SetStopTime(Seconds(100.0));
    
    // binning egress trace (not used)
    // receiver->TraceConnectWithoutContext("Rx", MakeCallback(&PacketArrival));

    // sender on ingress node
    Ptr<VariableDelaySender> sender = CreateObject<VariableDelaySender>();
    sender->SetRemote(interfaces.GetAddress(1), port);
    sender->SetDelayRandomVariable(delayRv);
    sender->SetIntervalRandomVariable(intervalRv);
    sender->SetPacketSize(1024);
    sender->SetMaxPackets(numPackets);
    sender->SetDelayMonitor(&delayMonitor);
    nodes.Get(0)->AddApplication(sender);
    sender->SetStartTime(Seconds(0.01));
    sender->SetStopTime(Seconds(100.0));

    // binning ingress trace (not used)
    // sender->TraceConnectWithoutContext("Tx", MakeCallback(&PacketDeparture));

    // run and clean up

    Simulator::Run();
    NS_LOG_INFO("Simulation complete. Packets received: " << receiver->GetReceived());

    // if no output file was specified, fall back to the default per-distribution name
    if (outputFile.empty())
    {
        outputFile = "../delay-monitoring/results/delay_samples_" + delayDist + ".csv";
    }
    delayMonitor.ExportToCSV(outputFile);

    // binning monitor export (not used)
    // g_ingressMonitor->PrintSummary();
    // g_egressMonitor->PrintSummary();
    // g_ingressMonitor->ExportToFile("../delay-monitoring/results/ingress_bins");
    // g_egressMonitor->ExportToFile("../delay-monitoring/results/egress_bins");
    // delete g_ingressMonitor;
    // delete g_egressMonitor;

    Simulator::Destroy();
    
    return 0;
}