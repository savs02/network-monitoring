// Multi-hop capacity use-case simulation
//
// A monitored probe flow traverses a chain of hopCount point-to-point links.
// Controlled cross traffic can be applied to every hop, to the full path, or
// to one selected hop. The receiver records end-to-end probe delay, while
// endpoint-visible probe and cross-traffic delivery counters are exported for
// comparison with distributional profiling. Queue-disc counters are optional
// debug fields and are disabled by default.

#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/ipv4-global-routing-helper.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/traffic-control-module.h"
#include "delay-monitor.h"
#include "variable-delay-application.h"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("MultiHopCapacity");

static uint64_t g_crossTrafficTxPackets = 0;
static uint64_t g_crossTrafficTxBytes = 0;
static uint64_t g_crossTrafficRxPackets = 0;
static uint64_t g_crossTrafficRxBytes = 0;

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

static std::vector<std::string>
SplitCommaSeparated(const std::string& value)
{
    std::vector<std::string> parts;
    std::stringstream stream(value);
    std::string item;
    while (std::getline(stream, item, ','))
    {
        item.erase(std::remove_if(item.begin(),
                                  item.end(),
                                  [](unsigned char c) { return std::isspace(c); }),
                   item.end());
        if (!item.empty())
        {
            parts.push_back(item);
        }
    }
    return parts;
}

static Ptr<RandomVariableStream>
CreateDelayRandomVariable(const std::string& delayDist,
                          double lognormalMu,
                          double lognormalSigma,
                          double weibullScale,
                          double weibullShape,
                          double normalMean,
                          double normalVariance)
{
    if (delayDist == "lognormal")
    {
        Ptr<LogNormalRandomVariable> rv = CreateObject<LogNormalRandomVariable>();
        rv->SetAttribute("Mu", DoubleValue(lognormalMu));
        rv->SetAttribute("Sigma", DoubleValue(lognormalSigma));
        return rv;
    }
    if (delayDist == "weibull")
    {
        Ptr<WeibullRandomVariable> rv = CreateObject<WeibullRandomVariable>();
        rv->SetAttribute("Scale", DoubleValue(weibullScale));
        rv->SetAttribute("Shape", DoubleValue(weibullShape));
        return rv;
    }

    Ptr<NormalRandomVariable> rv = CreateObject<NormalRandomVariable>();
    rv->SetAttribute("Mean", DoubleValue(normalMean));
    rv->SetAttribute("Variance", DoubleValue(normalVariance));
    return rv;
}

int
main(int argc, char* argv[])
{
    std::string delayDist = "weibull";
    double lognormalMu = 2.3;
    double lognormalSigma = 0.2;
    double weibullScale = 10.0;
    double weibullShape = 2.0;
    double normalMean = 40.0;
    double normalVariance = 4.0;

    uint32_t hopCount = 2;
    int32_t bottleneckHop = -1;
    uint32_t numPackets = 4000;
    uint32_t packetSize = 64;
    double intervalMean = 10.0;
    double simulationStopTime = 120.0;

    std::string linkDataRate = "10Mbps";
    std::string linkDataRates = "";
    std::string linkDelay = "2ms";
    uint32_t queueSize = 50;
    std::string queueDiscType = "ns3::FifoQueueDisc";
    bool useQueueDisc = false;
    std::string crossTrafficDataRate = "";
    std::string crossTrafficScope = "path";
    double crossTrafficStartTime = 0.0;
    double crossTrafficStopTime = -1.0;
    std::string crossTrafficPattern = "constant";
    std::string crossTrafficOnTime = "ns3::ConstantRandomVariable[Constant=1]";
    std::string crossTrafficOffTime = "ns3::ConstantRandomVariable[Constant=0]";

    std::string outputFile = "";
    std::string dropStatsFile = "";
    bool verbose = false;

    CommandLine cmd(__FILE__);
    cmd.AddValue("delayDist", "Delay distribution: normal, lognormal, weibull", delayDist);
    cmd.AddValue("lognormal_mu", "LogNormal mu parameter", lognormalMu);
    cmd.AddValue("lognormal_sigma", "LogNormal sigma parameter", lognormalSigma);
    cmd.AddValue("weibull_scale", "Weibull scale parameter", weibullScale);
    cmd.AddValue("weibull_shape", "Weibull shape parameter", weibullShape);
    cmd.AddValue("normal_mean", "Normal mean parameter", normalMean);
    cmd.AddValue("normal_variance", "Normal variance parameter", normalVariance);
    cmd.AddValue("hopCount", "Number of point-to-point links in the chain", hopCount);
    cmd.AddValue("bottleneckHop", "Zero-based hop used only when crossTrafficScope=single-hop. Negative selects the middle hop", bottleneckHop);
    cmd.AddValue("numPackets", "Number of probe packets to send", numPackets);
    cmd.AddValue("packetSize", "Probe packet size in bytes", packetSize);
    cmd.AddValue("intervalMean", "Mean inter-probe interval in ms", intervalMean);
    cmd.AddValue("simulationStopTime", "Simulation stop time in seconds", simulationStopTime);
    cmd.AddValue("linkDataRate", "Point-to-point link data rate", linkDataRate);
    cmd.AddValue("linkDataRates", "Optional comma-separated per-hop data rates. When set, length must equal hopCount", linkDataRates);
    cmd.AddValue("linkDelay", "Point-to-point propagation delay per hop", linkDelay);
    cmd.AddValue("queueSize", "Finite device queue size in packets", queueSize);
    cmd.AddValue("queueDiscType", "Traffic-control queue disc type", queueDiscType);
    cmd.AddValue("useQueueDisc", "Install a traffic-control queue disc. Disabled for observable-loss experiments", useQueueDisc);
    cmd.AddValue("crossTrafficDataRate", "Absolute cross-traffic data rate, e.g. 8Mbps", crossTrafficDataRate);
    cmd.AddValue("crossTrafficScope", "Cross-traffic placement: all-links, path, or single-hop", crossTrafficScope);
    cmd.AddValue("crossTrafficStartTime", "Cross-traffic start time in seconds", crossTrafficStartTime);
    cmd.AddValue("crossTrafficStopTime", "Cross-traffic stop time in seconds. Negative leaves drain time before simulation stop", crossTrafficStopTime);
    cmd.AddValue("crossTrafficPattern", "Cross-traffic pattern label: constant or bursty", crossTrafficPattern);
    cmd.AddValue("crossTrafficOnTime", "OnOffApplication OnTime random variable string", crossTrafficOnTime);
    cmd.AddValue("crossTrafficOffTime", "OnOffApplication OffTime random variable string", crossTrafficOffTime);
    cmd.AddValue("outputFile", "Output CSV path for delay samples", outputFile);
    cmd.AddValue("dropStatsFile", "Output CSV path for drop statistics", dropStatsFile);
    cmd.AddValue("verbose", "Enable NS_LOG_INFO output", verbose);
    cmd.Parse(argc, argv);

    if (hopCount < 1)
    {
        hopCount = 1;
    }
    uint32_t bottleneckIndex = bottleneckHop < 0
                                   ? std::min(hopCount - 1, hopCount / 2)
                                   : std::min(hopCount - 1, static_cast<uint32_t>(bottleneckHop));
    std::vector<std::string> perHopLinkRates = SplitCommaSeparated(linkDataRates);
    if (!perHopLinkRates.empty() && perHopLinkRates.size() != hopCount)
    {
        NS_FATAL_ERROR("linkDataRates must contain exactly one rate per hop when provided");
    }

    Time::SetResolution(Time::NS);
    if (verbose)
    {
        LogComponentEnable("MultiHopCapacity", LOG_LEVEL_INFO);
        LogComponentEnable("VariableDelayApplication", LOG_LEVEL_INFO);
    }

    DelayMonitor delayMonitor;

    NodeContainer nodes;
    nodes.Create(hopCount + 1);

    InternetStackHelper stack;
    stack.Install(nodes);

    PointToPointHelper p2p;
    p2p.SetChannelAttribute("Delay", StringValue(linkDelay));
    p2p.SetQueue("ns3::DropTailQueue<Packet>",
                 "MaxSize",
                 QueueSizeValue(QueueSize(std::to_string(queueSize) + "p")));

    TrafficControlHelper trafficControl;
    if (useQueueDisc)
    {
        trafficControl.SetRootQueueDisc(queueDiscType,
                                        "MaxSize",
                                        QueueSizeValue(QueueSize(std::to_string(queueSize) + "p")));
    }

    std::vector<NetDeviceContainer> devices;
    std::vector<Ipv4InterfaceContainer> interfaces;
    std::vector<Ptr<QueueDisc>> forwardQueueDiscs;
    std::vector<Ptr<Queue<Packet>>> forwardDeviceQueues;

    for (uint32_t i = 0; i < hopCount; ++i)
    {
        NodeContainer link(nodes.Get(i), nodes.Get(i + 1));
        const std::string rate = perHopLinkRates.empty() ? linkDataRate : perHopLinkRates[i];
        p2p.SetDeviceAttribute("DataRate", StringValue(rate));
        NetDeviceContainer dev = p2p.Install(link);
        Ptr<QueueDisc> forwardDisc;
        if (useQueueDisc)
        {
            QueueDiscContainer qdiscs = trafficControl.Install(dev);
            forwardDisc = qdiscs.Get(0);
        }

        Ipv4AddressHelper address;
        std::ostringstream subnet;
        subnet << "10." << (i + 1) << ".1.0";
        address.SetBase(subnet.str().c_str(), "255.255.255.0");
        Ipv4InterfaceContainer iface = address.Assign(dev);

        Ptr<PointToPointNetDevice> forwardDevice = DynamicCast<PointToPointNetDevice>(dev.Get(0));
        forwardDeviceQueues.push_back(forwardDevice ? forwardDevice->GetQueue() : nullptr);
        forwardQueueDiscs.push_back(forwardDisc);
        devices.push_back(dev);
        interfaces.push_back(iface);
    }

    Ipv4GlobalRoutingHelper::PopulateRoutingTables();

    Ptr<ExponentialRandomVariable> intervalRv = CreateObject<ExponentialRandomVariable>();
    intervalRv->SetAttribute("Mean", DoubleValue(intervalMean));

    Ptr<RandomVariableStream> delayRv =
        CreateDelayRandomVariable(delayDist,
                                  lognormalMu,
                                  lognormalSigma,
                                  weibullScale,
                                  weibullShape,
                                  normalMean,
                                  normalVariance);

    uint16_t probePort = 9;
    Ptr<VariableDelayReceiver> receiver = CreateObject<VariableDelayReceiver>();
    receiver->SetPort(probePort);
    receiver->SetDelayMonitor(&delayMonitor);
    nodes.Get(hopCount)->AddApplication(receiver);
    receiver->SetStartTime(Seconds(0.0));
    receiver->SetStopTime(Seconds(simulationStopTime));

    Ptr<VariableDelaySender> sender = CreateObject<VariableDelaySender>();
    sender->SetRemote(interfaces.back().GetAddress(1), probePort);
    sender->SetIntervalRandomVariable(intervalRv);
    sender->SetDelayRandomVariable(delayRv);
    sender->SetPacketSize(packetSize);
    sender->SetMaxPackets(numPackets);
    sender->SetRealisticMode(true);
    nodes.Get(0)->AddApplication(sender);
    sender->SetStartTime(Seconds(0.01));
    sender->SetStopTime(Seconds(simulationStopTime));

    std::vector<Ptr<PacketSink>> crossTrafficSinks;
    if (!crossTrafficDataRate.empty())
    {
        auto installCrossTraffic = [&](uint32_t sourceNode,
                                       uint32_t sinkNode,
                                       Ipv4Address sinkAddress,
                                       uint16_t port) {
            double ctStopTime = crossTrafficStopTime >= 0.0
                                    ? crossTrafficStopTime
                                    : std::max(crossTrafficStartTime, simulationStopTime - 1.0);
            PacketSinkHelper sink("ns3::UdpSocketFactory",
                                  InetSocketAddress(Ipv4Address::GetAny(), port));
            ApplicationContainer sinkApps = sink.Install(nodes.Get(sinkNode));
            sinkApps.Start(Seconds(0.0));
            sinkApps.Stop(Seconds(simulationStopTime));
            crossTrafficSinks.push_back(DynamicCast<PacketSink>(sinkApps.Get(0)));
            sinkApps.Get(0)->TraceConnectWithoutContext("Rx", MakeCallback(&CrossTrafficRxTrace));

            OnOffHelper onoff("ns3::UdpSocketFactory", InetSocketAddress(sinkAddress, port));
            onoff.SetConstantRate(DataRate(crossTrafficDataRate), 1024);
            onoff.SetAttribute("OnTime", StringValue(crossTrafficOnTime));
            onoff.SetAttribute("OffTime", StringValue(crossTrafficOffTime));
            ApplicationContainer crossTrafficApps = onoff.Install(nodes.Get(sourceNode));
            crossTrafficApps.Get(0)->TraceConnectWithoutContext("Tx", MakeCallback(&CrossTrafficTxTrace));
            crossTrafficApps.Start(Seconds(crossTrafficStartTime));
            crossTrafficApps.Stop(Seconds(ctStopTime));
        };

        if (crossTrafficScope == "single-hop")
        {
            installCrossTraffic(bottleneckIndex,
                                bottleneckIndex + 1,
                                interfaces[bottleneckIndex].GetAddress(1),
                                10);
        }
        else if (crossTrafficScope == "path")
        {
            installCrossTraffic(0, hopCount, interfaces.back().GetAddress(1), 10);
        }
        else
        {
            crossTrafficScope = "all-links";
            for (uint32_t i = 0; i < hopCount; ++i)
            {
                installCrossTraffic(i, i + 1, interfaces[i].GetAddress(1), 10 + i);
            }
        }
    }

    Simulator::Stop(Seconds(simulationStopTime));
    Simulator::Run();

    if (outputFile.empty())
    {
        outputFile = "../delay-monitoring/results/multi_hop_delay_samples.csv";
    }
    delayMonitor.ExportToCSV(outputFile);

    if (!dropStatsFile.empty())
    {
        uint32_t receivedProbes = delayMonitor.GetSampleCount();
        uint32_t lostProbes = receivedProbes >= numPackets ? 0 : numPackets - receivedProbes;
        uint64_t deviceDrops = 0;
        for (const auto& queue : forwardDeviceQueues)
        {
            if (queue)
            {
                deviceDrops += queue->GetTotalDroppedPackets();
            }
        }

        uint64_t qdiscDrops = 0;
        uint64_t qdiscBefore = 0;
        uint64_t qdiscAfter = 0;
        uint64_t qdiscMarks = 0;
        uint64_t qdiscReceived = 0;
        uint64_t qdiscSent = 0;
        uint64_t selectedHopDrops = 0;
        uint64_t maxHopDrops = 0;
        uint32_t maxHopDropIndex = 0;
        for (uint32_t i = 0; i < forwardQueueDiscs.size(); ++i)
        {
            if (!forwardQueueDiscs[i])
            {
                continue;
            }
            QueueDisc::Stats stats = forwardQueueDiscs[i]->GetStats();
            qdiscDrops += stats.nTotalDroppedPackets;
            qdiscBefore += stats.nTotalDroppedPacketsBeforeEnqueue;
            qdiscAfter += stats.nTotalDroppedPacketsAfterDequeue;
            qdiscMarks += stats.nTotalMarkedPackets;
            qdiscReceived += stats.nTotalReceivedPackets;
            qdiscSent += stats.nTotalSentPackets;
            if (i == bottleneckIndex)
            {
                selectedHopDrops = stats.nTotalDroppedPackets;
            }
            if (stats.nTotalDroppedPackets > maxHopDrops)
            {
                maxHopDrops = stats.nTotalDroppedPackets;
                maxHopDropIndex = i;
            }
        }
        uint64_t compatibilityHopDrops =
            crossTrafficScope == "single-hop" ? selectedHopDrops : maxHopDrops;
        uint32_t compatibilityHopIndex =
            crossTrafficScope == "single-hop" ? bottleneckIndex : maxHopDropIndex;

        uint64_t crossTrafficLoss =
            g_crossTrafficTxPackets >= g_crossTrafficRxPackets
                ? g_crossTrafficTxPackets - g_crossTrafficRxPackets
                : 0;

        std::ofstream drops(dropStatsFile);
        if (drops.is_open())
        {
            drops << "hop_count,bottleneck_hop,sent_probe_packets,received_probe_packets,"
                  << "cross_traffic_tx_packets,cross_traffic_rx_packets,"
                  << "cross_traffic_loss_count,cross_traffic_tx_bytes,"
                  << "cross_traffic_rx_bytes,active_cross_traffic_flows,"
                  << "cross_traffic_scope,use_queue_disc,"
                  << "probe_loss_count,queue_drop_count,qdisc_drop_count,"
                  << "bottleneck_qdisc_drop_count,qdisc_drop_before_enqueue_count,"
                  << "qdisc_drop_after_dequeue_count,qdisc_mark_count,"
                  << "qdisc_received_packets,qdisc_sent_packets,"
                  << "max_hop_qdisc_drop_count,max_hop_qdisc_drop_hop\n";
            drops << hopCount << "," << compatibilityHopIndex << ","
                  << numPackets << "," << receivedProbes << ","
                  << g_crossTrafficTxPackets << "," << g_crossTrafficRxPackets << ","
                  << crossTrafficLoss << "," << g_crossTrafficTxBytes << ","
                  << g_crossTrafficRxBytes << "," << crossTrafficSinks.size() << ","
                  << crossTrafficScope << "," << (useQueueDisc ? 1 : 0) << ","
                  << lostProbes << ","
                  << deviceDrops << "," << qdiscDrops << "," << compatibilityHopDrops << ","
                  << qdiscBefore << "," << qdiscAfter << "," << qdiscMarks << ","
                  << qdiscReceived << "," << qdiscSent << ","
                  << maxHopDrops << "," << maxHopDropIndex << "\n";
        }
    }

    Simulator::Destroy();
    return 0;
}
