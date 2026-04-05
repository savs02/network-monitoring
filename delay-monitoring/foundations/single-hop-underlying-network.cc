// Single-hop network simulation
//
//       10.1.1.0
// n0 -------------- n1
//    point-to-point
//
// Two experiment modes:
//
//   Theoretical / packet-loss:
//     Sender applies an artificial delay sampled from the chosen distribution.
//     DelayMonitor attached to the sender records the sampled delay directly.
//
//   Cross-traffic (--crossTrafficRate > 0):
//     No artificial delay. A second OnOff UDP sender injects background traffic
//     at the specified fraction of link capacity. Probe packets carry a
//     TimestampTag; DelayMonitor attached to the receiver measures real
//     end-to-end delay (propagation + queuing).

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/applications-module.h"
#include "variable-delay-application.h"
#include "delay-monitor.h"

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("SingleHop");

int
main(int argc, char* argv[])
{
    // --- Distribution parameters ---

    std::string delayDist = "normal";

    double lognormal_mu    = 2.3;
    double lognormal_sigma = 0.2;

    double weibull_scale = 10.0;
    double weibull_shape = 2.0;

    double normal_mean     = 40.0;
    double normal_variance = 4.0;

    uint32_t binomial_trials = 20;
    double   binomial_prob   = 0.5; // mean delay = trials * prob ms

    uint32_t zipf_n     = 20;  // support {1, ..., N}
    double   zipf_alpha = 1.5; // exponent — higher alpha concentrates more mass on small values

    // --- Traffic parameters ---

    uint32_t numPackets   = 100;
    double   lossRate     = 0.0; // fraction of packets dropped before reaching the monitor
    double   intervalMean = 1.0; // mean inter-packet time in ms (exponential)

    // --- Cross-traffic parameters ---

    bool   crossTrafficMode      = false;
    double crossTrafficRate      = 0.0; // fraction of link capacity
    double crossTrafficStartTime = 0.0; // seconds

    std::string linkDataRate = "10Mbps";
    std::string linkDelay    = "2ms";

    // --- Output ---

    std::string outputFile = "";

    // --- Command-line interface ---

    CommandLine cmd(__FILE__);
    cmd.AddValue("delayDist",             "Delay distribution: lognormal, weibull, normal, binomial, zipf, piecewise", delayDist);
    cmd.AddValue("lognormal_mu",          "LogNormal mu parameter", lognormal_mu);
    cmd.AddValue("lognormal_sigma",       "LogNormal sigma parameter", lognormal_sigma);
    cmd.AddValue("weibull_scale",         "Weibull scale parameter", weibull_scale);
    cmd.AddValue("weibull_shape",         "Weibull shape parameter", weibull_shape);
    cmd.AddValue("normal_mean",           "Normal mean parameter", normal_mean);
    cmd.AddValue("normal_variance",       "Normal variance parameter", normal_variance);
    cmd.AddValue("binomial_trials",       "Binomial number of trials (N)", binomial_trials);
    cmd.AddValue("binomial_prob",         "Binomial success probability (p)", binomial_prob);
    cmd.AddValue("zipf_n",                "Zipf upper bound N — support is {1, ..., N}", zipf_n);
    cmd.AddValue("zipf_alpha",            "Zipf exponent alpha", zipf_alpha);
    cmd.AddValue("numPackets",            "Number of packets to send", numPackets);
    cmd.AddValue("lossRate",              "Fraction of packets dropped before reaching the monitor (0 = no loss)", lossRate);
    cmd.AddValue("intervalMean",          "Mean inter-packet interval in ms (exponential)", intervalMean);
    cmd.AddValue("crossTrafficMode",      "Use receiver-side TimestampTag monitoring — cross-traffic experiment", crossTrafficMode);
    cmd.AddValue("crossTrafficRate",      "Fraction of link capacity used by cross-traffic (0 = theoretical)", crossTrafficRate);
    cmd.AddValue("crossTrafficStartTime", "Simulation time (s) at which the cross-traffic sender starts", crossTrafficStartTime);
    cmd.AddValue("linkDataRate",          "Point-to-point link data rate (cross-traffic experiment)", linkDataRate);
    cmd.AddValue("linkDelay",             "Point-to-point link propagation delay (cross-traffic experiment)", linkDelay);
    cmd.AddValue("outputFile",            "Output CSV path for delay samples (default: results/delay_samples_{dist}.csv)", outputFile);
    cmd.Parse(argc, argv);

    Time::SetResolution(Time::NS);
    LogComponentEnable("SingleHop", LOG_LEVEL_INFO);
    LogComponentEnable("VariableDelayApplication", LOG_LEVEL_INFO);

    NS_LOG_INFO("=== Two-node network: " << delayDist << ", " << numPackets << " packets ===");
    NS_LOG_INFO("Inter-packet interval: Exponential with mean " << intervalMean << " ms");

    // --- Network topology ---

    DelayMonitor delayMonitor;

    NodeContainer nodes;
    nodes.Create(2);

    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate", StringValue(linkDataRate));
    p2p.SetChannelAttribute("Delay",   StringValue(linkDelay));

    NetDeviceContainer devices = p2p.Install(nodes);

    InternetStackHelper stack;
    stack.Install(nodes);

    Ipv4AddressHelper address;
    address.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer interfaces = address.Assign(devices);

    // --- Delay distribution ---

    Ptr<RandomVariableStream> delayRv;

    if (delayDist == "lognormal")
    {
        Ptr<LogNormalRandomVariable> rv = CreateObject<LogNormalRandomVariable>();
        rv->SetAttribute("Mu",    DoubleValue(lognormal_mu));
        rv->SetAttribute("Sigma", DoubleValue(lognormal_sigma));
        delayRv = rv;
        NS_LOG_INFO("LogNormal: Mu=" << lognormal_mu << ", Sigma=" << lognormal_sigma);
    }
    else if (delayDist == "weibull")
    {
        Ptr<WeibullRandomVariable> rv = CreateObject<WeibullRandomVariable>();
        rv->SetAttribute("Scale", DoubleValue(weibull_scale));
        rv->SetAttribute("Shape", DoubleValue(weibull_shape));
        delayRv = rv;
        NS_LOG_INFO("Weibull: Scale=" << weibull_scale << ", Shape=" << weibull_shape);
    }
    else if (delayDist == "normal")
    {
        Ptr<NormalRandomVariable> rv = CreateObject<NormalRandomVariable>();
        rv->SetAttribute("Mean",     DoubleValue(normal_mean));
        rv->SetAttribute("Variance", DoubleValue(normal_variance));
        delayRv = rv;
        NS_LOG_INFO("Normal: Mean=" << normal_mean << ", Variance=" << normal_variance);
    }
    else if (delayDist == "binomial")
    {
        Ptr<BinomialRandomVariable> rv = CreateObject<BinomialRandomVariable>();
        rv->SetAttribute("Trials",      IntegerValue(binomial_trials));
        rv->SetAttribute("Probability", DoubleValue(binomial_prob));
        delayRv = rv;
        NS_LOG_INFO("Binomial: Trials=" << binomial_trials << ", Prob=" << binomial_prob
                    << " (mean=" << binomial_trials * binomial_prob << " ms)");
    }
    else if (delayDist == "zipf")
    {
        Ptr<ZipfRandomVariable> rv = CreateObject<ZipfRandomVariable>();
        rv->SetAttribute("N",     IntegerValue(zipf_n));
        rv->SetAttribute("Alpha", DoubleValue(zipf_alpha));
        delayRv = rv;
        NS_LOG_INFO("Zipf: N=" << zipf_n << ", Alpha=" << zipf_alpha);
    }
    else if (delayDist == "piecewise")
    {
        // Irregular multi-modal PMF over {1,...,20} — peaks at 1, 5, 8, 10, 12.
        // Probabilities: [0.12,0.02,0.08,0.01,0.10,0.03,0.07,0.12,0.02,0.09,
        //                 0.01,0.08,0.04,0.06,0.02,0.05,0.02,0.04,0.01,0.01]
        Ptr<EmpiricalRandomVariable> rv = CreateObject<EmpiricalRandomVariable>();
        rv->SetInterpolate(false);
        rv->CDF(0.0,  0.00);
        rv->CDF(1.0,  0.12);
        rv->CDF(2.0,  0.14);
        rv->CDF(3.0,  0.22);
        rv->CDF(4.0,  0.23);
        rv->CDF(5.0,  0.33);
        rv->CDF(6.0,  0.36);
        rv->CDF(7.0,  0.43);
        rv->CDF(8.0,  0.55);
        rv->CDF(9.0,  0.57);
        rv->CDF(10.0, 0.66);
        rv->CDF(11.0, 0.67);
        rv->CDF(12.0, 0.75);
        rv->CDF(13.0, 0.79);
        rv->CDF(14.0, 0.85);
        rv->CDF(15.0, 0.87);
        rv->CDF(16.0, 0.92);
        rv->CDF(17.0, 0.94);
        rv->CDF(18.0, 0.98);
        rv->CDF(19.0, 0.99);
        rv->CDF(20.0, 1.00);
        delayRv = rv;
        NS_LOG_INFO("Piecewise: irregular multi-modal PMF over {1,...,20}");
    }
    else
    {
        NS_FATAL_ERROR("Unknown distribution: " << delayDist);
    }

    // --- Applications ---

    Ptr<ExponentialRandomVariable> intervalRv = CreateObject<ExponentialRandomVariable>();
    intervalRv->SetAttribute("Mean", DoubleValue(intervalMean));

    uint16_t port = 9;

    Ptr<VariableDelayReceiver> receiver = CreateObject<VariableDelayReceiver>();
    receiver->SetPort(port);
    nodes.Get(1)->AddApplication(receiver);
    receiver->SetStartTime(Seconds(0.0));
    receiver->SetStopTime(Seconds(1000.0));

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
        // Probe sender still applies an artificial delay from the chosen distribution.
        // The TimestampTag is stamped before the artificial delay, so the receiver
        // measures total E2E = base_delay + propagation + queuing from cross-traffic.
        sender->SetDelayRandomVariable(delayRv);
        receiver->SetDelayMonitor(&delayMonitor);

        // Parse link rate string (e.g. "10Mbps") to compute the cross-traffic data rate.
        double linkBps = 0.0;
        if      (linkDataRate.find("Gbps") != std::string::npos)
            linkBps = std::stod(linkDataRate.substr(0, linkDataRate.find("Gbps"))) * 1e9;
        else if (linkDataRate.find("Mbps") != std::string::npos)
            linkBps = std::stod(linkDataRate.substr(0, linkDataRate.find("Mbps"))) * 1e6;
        else if (linkDataRate.find("Kbps") != std::string::npos)
            linkBps = std::stod(linkDataRate.substr(0, linkDataRate.find("Kbps"))) * 1e3;
        else
            linkBps = std::stod(linkDataRate); // assume bps

        std::ostringstream ctRateStr;
        ctRateStr << static_cast<uint64_t>(crossTrafficRate * linkBps) << "bps";

        NS_LOG_INFO("Cross-traffic: " << ctRateStr.str()
                    << " (" << (crossTrafficRate * 100) << "% of " << linkDataRate << ")");

        if (crossTrafficRate > 0.0)
        {
            uint16_t ctPort = 10;

            PacketSinkHelper sink("ns3::UdpSocketFactory",
                                  InetSocketAddress(Ipv4Address::GetAny(), ctPort));
            ApplicationContainer sinkApps = sink.Install(nodes.Get(1));
            sinkApps.Start(Seconds(0.0));
            sinkApps.Stop(Seconds(1000.0));

            OnOffHelper onoff("ns3::UdpSocketFactory",
                              InetSocketAddress(interfaces.GetAddress(1), ctPort));
            onoff.SetConstantRate(DataRate(ctRateStr.str()), 1024);
            onoff.SetAttribute("OnTime",  StringValue("ns3::ConstantRandomVariable[Constant=1]"));
            onoff.SetAttribute("OffTime", StringValue("ns3::ConstantRandomVariable[Constant=0]"));
            ApplicationContainer ctApps = onoff.Install(nodes.Get(0));
            ctApps.Start(Seconds(crossTrafficStartTime));
            ctApps.Stop(Seconds(1000.0));
        }
    }
    else
    {
        // Theoretical / packet-loss: sample directly from the distribution and record.
        // No packet is sent over the wire.
        sender->SetDelayRandomVariable(delayRv);
        sender->SetDelayMonitor(&delayMonitor);
        sender->SetTheoreticalMode(true);
    }

    // --- Run ---

    Simulator::Stop(Seconds(1000.0));
    Simulator::Run();
    NS_LOG_INFO("Simulation complete. Packets received: " << receiver->GetReceived());

    if (outputFile.empty())
        outputFile = "../delay-monitoring/results/delay_samples_" + delayDist + ".csv";

    delayMonitor.ExportToCSV(outputFile);
    Simulator::Destroy();

    return 0;
}
