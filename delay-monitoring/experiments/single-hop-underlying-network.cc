// Single Hop Network
//
//       10.1.1.0
// n0 -------------- n1
//    point-to-point
//
// Supports two modes:
//   Baseline / packet-loss / load-change experiments:
//     Sender applies artificial delay sampled from chosen distribution;
//     DelayMonitor attached to sender records sampled delay directly.
//
//   Cross-traffic experiment (--crossTrafficRate > 0):
//     No artificial delay; a second OnOff UDP sender on n0 injects
//     cross-traffic at the specified fraction of link capacity.
//     Probe packets carry a TimestampTag; DelayMonitor attached to
//     receiver measures real end-to-end delay (propagation + queuing).
//     Run via: run_cross_traffic_experiment.sh / cross_traffic_experiment.py

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/applications-module.h"
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

    // load/capacity experiment: M/M/1 sojourn time is Exponential(mean = base_delay / (1 - rho))
    // The shell script computes the mean for each utilisation level and passes it here.
    // (used by load_experiment.py — run via run_load_experiment.sh)
    double exponential_mean = 10.0; // ms
    
    uint32_t numPackets = 100;

    // packet loss experiment: fraction of packets independently lost before reaching the monitor
    // (used by packet_loss_experiment.py — run via run_packet_loss_experiment.sh)
    double lossRate = 0.0;

    // interval distribution parameters
    double intervalMean = 1.0; // mean inter-packet time in ms (exponential)

    // cross-traffic experiment: fraction of link capacity used by cross-traffic
    // Set crossTrafficMode=true to use receiver-side TimestampTag monitoring
    // (no artificial delay). crossTrafficRate=0 gives the no-load baseline.
    // Run via run_cross_traffic_experiment.sh / cross_traffic_experiment.py
    bool   crossTrafficMode = false;
    double crossTrafficRate = 0.0;

    // link parameters (relevant for cross-traffic experiment)
    std::string linkDataRate = "10Mbps";
    std::string linkDelay    = "2ms";

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
    cmd.AddValue("exponential_mean", "Exponential mean delay in ms (load/capacity experiment)", exponential_mean);
    cmd.AddValue("numPackets", "Number of packets to send", numPackets);
    cmd.AddValue("lossRate", "Fraction of packets independently lost before reaching the monitor, 0.0 = no loss (packet loss experiment)", lossRate);
    cmd.AddValue("intervalMean", "Mean inter-packet interval in ms (exponential)", intervalMean);
    cmd.AddValue("crossTrafficMode", "Use receiver-side TimestampTag monitoring (no artificial delay) — cross-traffic experiment", crossTrafficMode);
    cmd.AddValue("crossTrafficRate", "Fraction of link capacity used by cross-traffic (0 = baseline, cross-traffic experiment)", crossTrafficRate);
    cmd.AddValue("linkDataRate", "Point-to-point link data rate (cross-traffic experiment)", linkDataRate);
    cmd.AddValue("linkDelay", "Point-to-point link propagation delay (cross-traffic experiment)", linkDelay);
    cmd.AddValue("outputFile", "Output CSV path for delay samples (default: results/delay_samples_{dist}.csv)", outputFile);
    // cmd.AddValue("enableMonitoring", "Enable binning monitoring", enableMonitoring);
    // cmd.AddValue("binWidth", "Bin width in ms", binWidth);
    cmd.Parse(argc, argv);

    Time::SetResolution(Time::NS);
    LogComponentEnable("SingleHop", LOG_LEVEL_INFO);
    LogComponentEnable("VariableDelayApplication", LOG_LEVEL_INFO);

    NS_LOG_INFO("=== Two-Node Network: " << delayDist << ", " << numPackets << " packets ===");
    NS_LOG_INFO("Inter-packet interval: Exponential with mean " << intervalMean << "ms");

    // delay monitor — attached to sender (baseline) or receiver (cross-traffic)
    DelayMonitor delayMonitor;

    // set up the simple network topology

    NodeContainer nodes;
    nodes.Create(2);

    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate", StringValue(linkDataRate));
    p2p.SetChannelAttribute("Delay", StringValue(linkDelay));

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
    else if (delayDist == "exponential") {
        // load/capacity experiment: M/M/1 sojourn time distribution
        // mean = base_delay / (1 - rho), passed in via --exponential_mean
        Ptr<ExponentialRandomVariable> erv = CreateObject<ExponentialRandomVariable>();
        erv->SetAttribute("Mean", DoubleValue(exponential_mean));
        delayRv = erv;
        NS_LOG_INFO("Exponential: Mean=" << exponential_mean << "ms");
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
    receiver->SetStopTime(Seconds(1000.0));

    // sender on ingress node
    Ptr<VariableDelaySender> sender = CreateObject<VariableDelaySender>();
    sender->SetRemote(interfaces.GetAddress(1), port);
    sender->SetIntervalRandomVariable(intervalRv);
    sender->SetPacketSize(1024);
    sender->SetMaxPackets(numPackets);
    sender->SetLossRate(lossRate);
    nodes.Get(0)->AddApplication(sender);
    sender->SetStartTime(Seconds(0.01));
    sender->SetStopTime(Seconds(1000.0));

    if (crossTrafficMode)
    {
        // cross-traffic experiment:
        //   - probe sender still applies artificial delay from underlying distribution
        //   - DelayProbeTag stamped before artificial delay, so receiver measures:
        //       total E2E = base_delay + propagation + queuing_from_cross_traffic
        //   - DelayMonitor on receiver records this full observed delay
        sender->SetDelayRandomVariable(delayRv);
        receiver->SetDelayMonitor(&delayMonitor);

        // compute cross-traffic data rate string (bits/s as integer)
        // linkDataRate is e.g. "10Mbps" → 10e6 bps; crossTrafficRate is fraction 0..1
        // parse link rate: assume "NNNMbps" format
        double linkBps = 0.0;
        {
            std::string rate = linkDataRate;
            if (rate.find("Mbps") != std::string::npos)
                linkBps = std::stod(rate.substr(0, rate.find("Mbps"))) * 1e6;
            else if (rate.find("Gbps") != std::string::npos)
                linkBps = std::stod(rate.substr(0, rate.find("Gbps"))) * 1e9;
            else if (rate.find("Kbps") != std::string::npos)
                linkBps = std::stod(rate.substr(0, rate.find("Kbps"))) * 1e3;
            else
                linkBps = std::stod(rate);  // assume bps
        }
        double ctBps = crossTrafficRate * linkBps;
        std::ostringstream ctRateStr;
        ctRateStr << static_cast<uint64_t>(ctBps) << "bps";

        NS_LOG_INFO("Cross-traffic experiment: rate=" << ctRateStr.str()
                    << " (" << (crossTrafficRate * 100) << "% of " << linkDataRate << ")");

        // cross-traffic sender + sink — only when rate > 0 (baseline is 0%)
        if (crossTrafficRate > 0.0)
        {
            uint16_t ctPort = 10;
            PacketSinkHelper sink("ns3::UdpSocketFactory",
                                  InetSocketAddress(Ipv4Address::GetAny(), ctPort));
            ApplicationContainer sinkApps = sink.Install(nodes.Get(1));
            sinkApps.Start(Seconds(0.0));
            sinkApps.Stop(Seconds(1000.0));

            // OnOff cross-traffic sender on n0 → n1:port 10
            OnOffHelper onoff("ns3::UdpSocketFactory",
                              InetSocketAddress(interfaces.GetAddress(1), ctPort));
            onoff.SetConstantRate(DataRate(ctRateStr.str()), 1024);
            onoff.SetAttribute("OnTime",  StringValue("ns3::ConstantRandomVariable[Constant=1]"));
            onoff.SetAttribute("OffTime", StringValue("ns3::ConstantRandomVariable[Constant=0]"));
            ApplicationContainer ctApps = onoff.Install(nodes.Get(0));
            ctApps.Start(Seconds(0.0));
            ctApps.Stop(Seconds(1000.0));
        }
    }
    else
    {
        // baseline / packet-loss / load-change experiments:
        // artificial delay applied by sender; monitor records sampled delay directly
        sender->SetDelayRandomVariable(delayRv);
        sender->SetDelayMonitor(&delayMonitor);
    }

    // run and clean up

    Simulator::Stop(Seconds(1000.0));
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