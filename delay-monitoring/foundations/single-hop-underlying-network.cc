// Single-hop network simulation
//
//       10.1.1.0
// n0 -------------- n1
//    point-to-point
//
// Two experiment modes:
//
//   Direct sampling:
//     Sender applies an artificial delay sampled from the chosen distribution.
//     DelayMonitor attached to the sender records the sampled delay directly.
//
//   Offered-load / cross-traffic:
//     The probe sender applies the chosen base delay distribution, then sends
//     packets over the link. A second OnOff UDP sender can inject controlled
//     background traffic either as an absolute data rate or as a fraction of
//     link capacity. Probe packets carry a TimestampTag; DelayMonitor attached
//     to the receiver measures real end-to-end delay. Endpoint-visible probe
//     and cross-traffic delivery counters are exported for loss comparisons.

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/traffic-control-module.h"
#include "ns3/applications-module.h"
#include "variable-delay-application.h"
#include "delay-monitor.h"
#include <fstream>
#include <sstream>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("SingleHop");

static uint64_t g_queueTraceDrops = 0;
static uint64_t g_macTxDrops = 0;
static uint64_t g_phyTxDrops = 0;
static uint64_t g_crossTrafficTxPackets = 0;
static uint64_t g_crossTrafficTxBytes = 0;
static uint64_t g_crossTrafficRxPackets = 0;
static uint64_t g_crossTrafficRxBytes = 0;

static void
QueueDropTrace(Ptr<const Packet> packet)
{
    g_queueTraceDrops++;
}

static void
MacTxDropTrace(Ptr<const Packet> packet)
{
    g_macTxDrops++;
}

static void
PhyTxDropTrace(Ptr<const Packet> packet)
{
    g_phyTxDrops++;
}

static void
CrossTrafficTxTrace(Ptr<const Packet> packet)
{
    g_crossTrafficTxPackets++;
    g_crossTrafficTxBytes += packet->GetSize();
}

static void
CrossTrafficRxTrace(Ptr<const Packet> packet, const Address& from)
{
    g_crossTrafficRxPackets++;
    g_crossTrafficRxBytes += packet->GetSize();
}

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
    double   zipf_alpha = 1.5; // higher alpha concentrates more mass on small values

    // --- Traffic parameters ---

    uint32_t numPackets   = 100;
    uint32_t packetSize   = 1024;
    double   lossRate     = 0.0; // fraction of packets dropped before reaching the monitor
    double   intervalMean = 1.0; // mean inter-packet time in ms (exponential)
    double   simulationStopTime = 120.0;

    // --- Realistic mode parameters ---

    bool realisticMode = false; // sample sets floor delay; packet sent over wire; receiver records actual E2E

    // --- Cross-traffic parameters ---

    bool   crossTrafficMode      = false;
    double crossTrafficRate      = 0.0; // fraction of link capacity
    std::string crossTrafficDataRate = ""; // absolute offered load, e.g. 8Mbps
    double crossTrafficStartTime = 0.0; // seconds
    double crossTrafficStopTime = -1.0; // seconds, negative means stop before simulation drain
    std::string crossTrafficPattern = "constant";
    std::string crossTrafficOnTime = "ns3::ConstantRandomVariable[Constant=1]";
    std::string crossTrafficOffTime = "ns3::ConstantRandomVariable[Constant=0]";

    std::string linkDataRate = "10Mbps";
    std::string linkDelay    = "2ms";
    uint32_t    queueSize    = 50;  // DropTail queue depth in packets
    std::string queueDiscType = "ns3::FifoQueueDisc";
    bool        useQueueDisc = false;

    // --- Output ---

    std::string outputFile = "";
    std::string dropStatsFile = "";
    bool verbose = false;

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
    cmd.AddValue("zipf_n",                "Zipf upper bound N. Support is {1, ..., N}", zipf_n);
    cmd.AddValue("zipf_alpha",            "Zipf exponent alpha", zipf_alpha);
    cmd.AddValue("numPackets",            "Number of packets to send", numPackets);
    cmd.AddValue("packetSize",            "Probe packet size in bytes", packetSize);
    cmd.AddValue("lossRate",              "Fraction of packets dropped before reaching the monitor (0 = no loss)", lossRate);
    cmd.AddValue("intervalMean",          "Mean inter-packet interval in ms (exponential)", intervalMean);
    cmd.AddValue("simulationStopTime",     "Simulation stop time in seconds", simulationStopTime);
    cmd.AddValue("realisticMode",         "Sampled delay is a floor; packet sent over wire; receiver records actual E2E delay", realisticMode);
    cmd.AddValue("crossTrafficMode",      "Use receiver-side TimestampTag monitoring for cross-traffic experiments", crossTrafficMode);
    cmd.AddValue("crossTrafficRate",      "Fraction of link capacity used by cross-traffic (0 = theoretical)", crossTrafficRate);
    cmd.AddValue("crossTrafficDataRate",  "Absolute cross-traffic data rate, e.g. 8Mbps. Overrides crossTrafficRate when set", crossTrafficDataRate);
    cmd.AddValue("crossTrafficStartTime", "Simulation time (s) at which the cross-traffic sender starts", crossTrafficStartTime);
    cmd.AddValue("crossTrafficStopTime",  "Simulation time (s) at which the cross-traffic sender stops. Negative leaves drain time before simulation stop", crossTrafficStopTime);
    cmd.AddValue("crossTrafficPattern",   "Cross-traffic pattern label: constant or bursty", crossTrafficPattern);
    cmd.AddValue("crossTrafficOnTime",    "OnOffApplication OnTime random variable string", crossTrafficOnTime);
    cmd.AddValue("crossTrafficOffTime",   "OnOffApplication OffTime random variable string", crossTrafficOffTime);
    cmd.AddValue("linkDataRate",          "Point-to-point link data rate", linkDataRate);
    cmd.AddValue("linkDelay",             "Point-to-point link propagation delay", linkDelay);
    cmd.AddValue("queueSize",             "DropTail queue depth in packets", queueSize);
    cmd.AddValue("queueDiscType",         "Traffic-control queue disc type", queueDiscType);
    cmd.AddValue("useQueueDisc",          "Install a traffic-control queue disc. Disabled for observable-loss experiments", useQueueDisc);
    cmd.AddValue("outputFile",            "Output CSV path for delay samples (default: results/delay_samples_{dist}.csv)", outputFile);
    cmd.AddValue("dropStatsFile",         "Output CSV path for probe and queue drop statistics", dropStatsFile);
    cmd.AddValue("verbose",               "Enable NS_LOG_INFO output for debugging", verbose);
    cmd.Parse(argc, argv);

    Time::SetResolution(Time::NS);
    if (verbose)
    {
        LogComponentEnable("SingleHop", LOG_LEVEL_INFO);
        LogComponentEnable("VariableDelayApplication", LOG_LEVEL_INFO);
    }

    NS_LOG_INFO("=== Two-node network: " << delayDist << ", " << numPackets << " packets ===");
    NS_LOG_INFO("Inter-packet interval: Exponential with mean " << intervalMean << " ms");

    // --- Network topology ---

    DelayMonitor delayMonitor;

    NodeContainer nodes;
    nodes.Create(2);

    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate", StringValue(linkDataRate));
    p2p.SetChannelAttribute("Delay",   StringValue(linkDelay));
    p2p.SetQueue("ns3::DropTailQueue<Packet>",
                 "MaxSize", QueueSizeValue(QueueSize(std::to_string(queueSize) + "p")));

    NetDeviceContainer devices = p2p.Install(nodes);
    Ptr<PointToPointNetDevice> senderDevice = DynamicCast<PointToPointNetDevice>(devices.Get(0));
    Ptr<Queue<Packet>> senderQueue;
    if (senderDevice && senderDevice->GetQueue())
    {
        senderQueue = senderDevice->GetQueue();
        senderQueue->TraceConnectWithoutContext("Drop", MakeCallback(&QueueDropTrace));
        senderQueue->TraceConnectWithoutContext("DropBeforeEnqueue", MakeCallback(&QueueDropTrace));
        senderDevice->TraceConnectWithoutContext("MacTxDrop", MakeCallback(&MacTxDropTrace));
        senderDevice->TraceConnectWithoutContext("PhyTxDrop", MakeCallback(&PhyTxDropTrace));
    }

    InternetStackHelper stack;
    stack.Install(nodes);

    Ipv4AddressHelper address;
    address.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer interfaces = address.Assign(devices);
    Ptr<QueueDisc> rootQueueDisc;
    if (useQueueDisc)
    {
        TrafficControlHelper trafficControlHelper;
        trafficControlHelper.SetRootQueueDisc(
            queueDiscType,
            "MaxSize",
            QueueSizeValue(QueueSize(std::to_string(queueSize) + "p")));
        trafficControlHelper.Install(devices);
        Ptr<TrafficControlLayer> trafficControl = nodes.Get(0)->GetObject<TrafficControlLayer>();
        rootQueueDisc =
            trafficControl ? trafficControl->GetRootQueueDiscOnDevice(devices.Get(0)) : nullptr;
    }

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
        // Irregular multi-modal PMF over {1,...,20}, with peaks at 1, 5, 8, 10, 12.
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
    receiver->SetStopTime(Seconds(simulationStopTime));

    Ptr<VariableDelaySender> sender = CreateObject<VariableDelaySender>();
    sender->SetRemote(interfaces.GetAddress(1), port);
    sender->SetIntervalRandomVariable(intervalRv);
    sender->SetPacketSize(packetSize);
    sender->SetMaxPackets(numPackets);
    sender->SetLossRate(lossRate);
    nodes.Get(0)->AddApplication(sender);
    sender->SetStartTime(Seconds(0.01));
    sender->SetStopTime(Seconds(simulationStopTime));

    Ptr<PacketSink> crossTrafficSink;

    if (realisticMode)
    {
        // Sampled delay acts as a floor: the sender schedules each packet to leave
        // after at least the sampled delay, then the packet travels the real link.
        // The receiver measures total E2E (floor delay + propagation + transmission)
        // via DelayProbeTag. Use a negligible link delay and high data rate so the
        // network overhead is sub-millisecond and rounds away in the analysis.
        sender->SetDelayRandomVariable(delayRv);
        sender->SetRealisticMode(true);
        receiver->SetDelayMonitor(&delayMonitor);
        NS_LOG_INFO("Realistic mode: sampled delay is floor; receiver records actual E2E");
    }
    else if (crossTrafficMode)
    {
        // Probe sender still applies an artificial delay from the chosen distribution.
        // The TimestampTag is stamped before the artificial delay, so the receiver
        // measures total E2E = base_delay + propagation + queuing from cross-traffic.
        sender->SetDelayRandomVariable(delayRv);
        receiver->SetDelayMonitor(&delayMonitor);

        std::string ctRateString;
        if (!crossTrafficDataRate.empty())
        {
            ctRateString = crossTrafficDataRate;
        }
        else
        {
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
            ctRateString = ctRateStr.str();
        }

        NS_LOG_INFO("Cross-traffic: " << ctRateString << " pattern=" << crossTrafficPattern);

        if (crossTrafficRate > 0.0 || !crossTrafficDataRate.empty())
        {
            uint16_t ctPort = 10;
            double ctStopTime = crossTrafficStopTime >= 0.0
                                    ? crossTrafficStopTime
                                    : std::max(crossTrafficStartTime, simulationStopTime - 1.0);

            PacketSinkHelper sink("ns3::UdpSocketFactory",
                                  InetSocketAddress(Ipv4Address::GetAny(), ctPort));
            ApplicationContainer sinkApps = sink.Install(nodes.Get(1));
            sinkApps.Start(Seconds(0.0));
            sinkApps.Stop(Seconds(simulationStopTime));
            crossTrafficSink = DynamicCast<PacketSink>(sinkApps.Get(0));
            sinkApps.Get(0)->TraceConnectWithoutContext("Rx", MakeCallback(&CrossTrafficRxTrace));

            OnOffHelper onoff("ns3::UdpSocketFactory",
                              InetSocketAddress(interfaces.GetAddress(1), ctPort));
            onoff.SetConstantRate(DataRate(ctRateString), 1024);
            onoff.SetAttribute("OnTime",  StringValue(crossTrafficOnTime));
            onoff.SetAttribute("OffTime", StringValue(crossTrafficOffTime));
            ApplicationContainer ctApps = onoff.Install(nodes.Get(0));
            ctApps.Get(0)->TraceConnectWithoutContext("Tx", MakeCallback(&CrossTrafficTxTrace));
            ctApps.Start(Seconds(crossTrafficStartTime));
            ctApps.Stop(Seconds(ctStopTime));
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

    Simulator::Stop(Seconds(simulationStopTime));
    Simulator::Run();
    NS_LOG_INFO("Simulation complete. Packets received: " << receiver->GetReceived());

    if (outputFile.empty())
        outputFile = "../delay-monitoring/results/delay_samples_" + delayDist + ".csv";

    delayMonitor.ExportToCSV(outputFile);
    if (!dropStatsFile.empty())
    {
        std::ofstream drops(dropStatsFile);
        if (drops.is_open())
        {
            uint32_t receivedProbes = delayMonitor.GetSampleCount();
            uint32_t lostProbes = receivedProbes >= numPackets ? 0 : numPackets - receivedProbes;
            uint32_t queueDropsBeforeEnqueue = senderQueue ? senderQueue->GetTotalDroppedPacketsBeforeEnqueue() : 0;
            uint32_t queueDropsTotal = senderQueue ? senderQueue->GetTotalDroppedPackets() : 0;
            QueueDisc::Stats queueDiscStats;
            if (rootQueueDisc)
            {
                queueDiscStats = rootQueueDisc->GetStats();
            }
            drops << "sent_probe_packets,received_probe_packets,probe_loss_count,"
                  << "cross_traffic_tx_packets,cross_traffic_rx_packets,"
                  << "cross_traffic_loss_count,cross_traffic_tx_bytes,"
                  << "cross_traffic_rx_bytes,active_cross_traffic_flows,use_queue_disc,"
                  << "queue_drop_count,queue_drop_total_count,queue_trace_drop_count,"
                  << "mac_tx_drop_count,phy_tx_drop_count,"
                  << "qdisc_drop_count,qdisc_drop_before_enqueue_count,"
                  << "qdisc_drop_after_dequeue_count,qdisc_mark_count,"
                  << "qdisc_received_packets,qdisc_sent_packets\n";
            uint64_t crossTrafficLoss =
                g_crossTrafficTxPackets >= g_crossTrafficRxPackets
                    ? g_crossTrafficTxPackets - g_crossTrafficRxPackets
                    : 0;
            drops << numPackets << "," << receivedProbes << "," << lostProbes << ","
                  << g_crossTrafficTxPackets << "," << g_crossTrafficRxPackets << ","
                  << crossTrafficLoss << "," << g_crossTrafficTxBytes << ","
                  << g_crossTrafficRxBytes << ","
                  << (g_crossTrafficTxPackets > 0 ? 1 : 0) << ","
                  << (useQueueDisc ? 1 : 0) << ","
                  << queueDropsBeforeEnqueue << "," << queueDropsTotal << ","
                  << g_queueTraceDrops << "," << g_macTxDrops << "," << g_phyTxDrops << ","
                  << queueDiscStats.nTotalDroppedPackets << ","
                  << queueDiscStats.nTotalDroppedPacketsBeforeEnqueue << ","
                  << queueDiscStats.nTotalDroppedPacketsAfterDequeue << ","
                  << queueDiscStats.nTotalMarkedPackets << ","
                  << queueDiscStats.nTotalReceivedPackets << ","
                  << queueDiscStats.nTotalSentPackets << "\n";
        }
    }
    Simulator::Destroy();

    return 0;
}
