#include "variable-delay-application.h"
#include "ns3/log.h"
#include "ns3/socket.h"
#include "ns3/simulator.h"
#include "ns3/packet.h"
#include "ns3/udp-socket-factory.h"
#include "ns3/inet-socket-address.h"

namespace ns3 {

NS_LOG_COMPONENT_DEFINE("VariableDelayApplication");

// ---------------------------------------------------------------------------
// DelayProbeTag — carries probe-packet send time through the simulator so the
// receiver can compute the actual end-to-end delay.
// Used by the cross-traffic experiment (cross_traffic_experiment.py).
// ---------------------------------------------------------------------------

NS_OBJECT_ENSURE_REGISTERED(DelayProbeTag);

TypeId
DelayProbeTag::GetTypeId()
{
    static TypeId tid = TypeId("ns3::DelayProbeTag")
        .SetParent<Tag>()
        .AddConstructor<DelayProbeTag>();
    return tid;
}

TypeId
DelayProbeTag::GetInstanceTypeId() const
{
    return GetTypeId();
}

uint32_t
DelayProbeTag::GetSerializedSize() const
{
    return sizeof(uint64_t);   // 8 bytes for nanoseconds
}

void
DelayProbeTag::Serialize(TagBuffer buf) const
{
    buf.WriteU64(m_sentNs);
}

void
DelayProbeTag::Deserialize(TagBuffer buf)
{
    m_sentNs = buf.ReadU64();
}

void
DelayProbeTag::Print(std::ostream& os) const
{
    os << "sentNs=" << m_sentNs;
}

void
DelayProbeTag::SetSentNs(uint64_t ns)
{
    m_sentNs = ns;
}

uint64_t
DelayProbeTag::GetSentNs() const
{
    return m_sentNs;
}

// ---------------------------------------------------------------------------

NS_OBJECT_ENSURE_REGISTERED(VariableDelaySender);

TypeId
VariableDelaySender::GetTypeId()
{
    static TypeId tid = TypeId("ns3::VariableDelaySender")
        .SetParent<Application>()
        .SetGroupName("Applications")
        .AddConstructor<VariableDelaySender>()
        .AddTraceSource("Tx",
                        "A packet has been transmitted",
                        MakeTraceSourceAccessor(&VariableDelaySender::m_txTrace),
                        "ns3::Packet::AddressTracedCallback");
    return tid;
}

VariableDelaySender::VariableDelaySender()
    : m_socket(nullptr),
      m_peerAddress(Ipv4Address::GetAny()),
      m_peerPort(0),
      m_packetSize(1024),
      m_maxPackets(100),
      m_packetsSent(0),
      m_interval(MilliSeconds(100)),
      m_delayRv(nullptr),
      m_intervalRv(nullptr),
      m_delayMonitor(nullptr),
      m_theoreticalMode(false),
      m_realisticMode(false),
      m_lossRate(0.0),
      m_lossRv(CreateObject<UniformRandomVariable>())
{
}

VariableDelaySender::~VariableDelaySender()
{
}

void
VariableDelaySender::DoDispose()
{
    m_socket = nullptr;
    Application::DoDispose();
}

void
VariableDelaySender::SetRemote(Ipv4Address ip, uint16_t port)
{
    m_peerAddress = ip;
    m_peerPort = port;
}

void
VariableDelaySender::SetDelayRandomVariable(Ptr<RandomVariableStream> delay)
{
    m_delayRv = delay;
}

void
VariableDelaySender::SetIntervalRandomVariable(Ptr<RandomVariableStream> interval)
{
    m_intervalRv = interval;
}

void
VariableDelaySender::SetPacketSize(uint32_t packetSize)
{
    m_packetSize = packetSize;
}

void
VariableDelaySender::SetMaxPackets(uint32_t maxPackets)
{
    m_maxPackets = maxPackets;
}

void
VariableDelaySender::SetInterval(Time interval)
{
    m_interval = interval;
}

void
VariableDelaySender::SetDelayMonitor(DelayMonitor* monitor)
{
    m_delayMonitor = monitor;
}

void
VariableDelaySender::SetTheoreticalMode(bool theoretical)
{
    m_theoreticalMode = theoretical;
}

void
VariableDelaySender::SetRealisticMode(bool realistic)
{
    m_realisticMode = realistic;
}

void
VariableDelaySender::SetLossRate(double lossRate)
{
    m_lossRate = lossRate;
}

void
VariableDelaySender::StartApplication()
{
    if (!m_theoreticalMode && !m_socket)
    {
        TypeId tid = TypeId::LookupByName("ns3::UdpSocketFactory");
        m_socket = Socket::CreateSocket(GetNode(), tid);
        m_socket->Bind();
        m_socket->Connect(InetSocketAddress(m_peerAddress, m_peerPort));
    }

    m_packetsSent = 0;
    ScheduleTransmit(Seconds(0.0));
}

void
VariableDelaySender::StopApplication()
{
    if (m_sendEvent.IsPending())
    {
        Simulator::Cancel(m_sendEvent);
    }
    
    if (m_socket)
    {
        m_socket->Close();
    }
}

void
VariableDelaySender::ScheduleTransmit(Time dt)
{
    m_sendEvent = Simulator::Schedule(dt, &VariableDelaySender::SendPacket, this);
}

void
VariableDelaySender::SendPacket()
{
    if (m_packetsSent >= m_maxPackets)
    {
        return;
    }
    
    // sample the network delay from the distribution
    double sampledDelay = 0.0;
    if (m_delayRv)
    {
        sampledDelay = m_delayRv->GetValue();
        if (sampledDelay < 0) sampledDelay = 0;
    }

    NS_LOG_INFO("Packet " << m_packetsSent << ": sampled delay = " << sampledDelay << " ms");

    // packet loss experiment: independent Bernoulli drop per packet
    // packetReceived = false means the monitor never sees this packet
    bool packetReceived = (m_lossRate == 0.0) || (m_lossRv->GetValue(0.0, 1.0) >= m_lossRate);

    // in theoretical mode, record the sampled delay directly at the sender.
    // in realistic mode, the sampled delay is only a floor — the receiver
    // records the true end-to-end delay via DelayProbeTag instead.
    if (m_delayMonitor && packetReceived && !m_realisticMode)
        m_delayMonitor->RecordDelay(m_packetsSent, sampledDelay);

    // in theoretical mode the sample is all we need — no packet is sent
    if (!m_theoreticalMode)
    {
        Ptr<Packet> packet = Create<Packet>(m_packetSize);
        Address peerAddr = InetSocketAddress(m_peerAddress, m_peerPort);
        m_txTrace(packet, peerAddr);

        NS_LOG_INFO("Packet " << m_packetsSent << " entered ingress at t=" << Simulator::Now().GetSeconds() << "s");

        uint64_t sendNs = Simulator::Now().GetNanoSeconds();
        Time delayTime = (sampledDelay > 0.0) ? Seconds(sampledDelay * 1e-3) : NanoSeconds(1);
        uint32_t currentPacket = m_packetsSent;

        Simulator::Schedule(delayTime, [this, packet, currentPacket, sendNs]() {
            DelayProbeTag tsTag;
            tsTag.SetSentNs(sendNs);
            packet->AddPacketTag(tsTag);

            int sent = m_socket->Send(packet);
            if (sent > 0)
                NS_LOG_INFO("Packet " << currentPacket << " exited network at t=" << Simulator::Now().GetSeconds() << "s");
            else
                NS_LOG_ERROR("Failed to send packet " << currentPacket);
        });
    }
    
    m_packetsSent++;
    
    // schedule next packet - use random interval if set, otherwise fixed
    if (m_packetsSent < m_maxPackets)
    {
        Time nextInterval;
        if (m_intervalRv)
        {
            double sampledInterval = m_intervalRv->GetValue();
            if (sampledInterval < 0.01) sampledInterval = 0.01;  // minimum 0.01ms
            nextInterval = MilliSeconds(sampledInterval);
        }
        else
        {
            nextInterval = m_interval;
        }
        ScheduleTransmit(nextInterval);
    }
}

NS_OBJECT_ENSURE_REGISTERED(VariableDelayReceiver);

TypeId
VariableDelayReceiver::GetTypeId()
{
    static TypeId tid = TypeId("ns3::VariableDelayReceiver")
        .SetParent<Application>()
        .SetGroupName("Applications")
        .AddConstructor<VariableDelayReceiver>()
        .AddTraceSource("Rx",
                        "A packet has been received",
                        MakeTraceSourceAccessor(&VariableDelayReceiver::m_rxTrace),
                        "ns3::Packet::AddressTracedCallback");
    return tid;
}

VariableDelayReceiver::VariableDelayReceiver()
    : m_socket(nullptr),
      m_port(9),
      m_received(0),
      m_delayMonitor(nullptr)
{
}

VariableDelayReceiver::~VariableDelayReceiver()
{
}

void
VariableDelayReceiver::DoDispose()
{
    m_socket = nullptr;
    Application::DoDispose();
}

void
VariableDelayReceiver::SetPort(uint16_t port)
{
    m_port = port;
}

void
VariableDelayReceiver::SetDelayMonitor(DelayMonitor* monitor)
{
    m_delayMonitor = monitor;
}

uint32_t
VariableDelayReceiver::GetReceived() const
{
    return m_received;
}

void
VariableDelayReceiver::StartApplication()
{
    if (!m_socket)
    {
        TypeId tid = TypeId::LookupByName("ns3::UdpSocketFactory");
        m_socket = Socket::CreateSocket(GetNode(), tid);
        InetSocketAddress local = InetSocketAddress(Ipv4Address::GetAny(), m_port);
        if (m_socket->Bind(local) == -1)
        {
            NS_FATAL_ERROR("Failed to bind socket");
        }
    }
    
    m_socket->SetRecvCallback(MakeCallback(&VariableDelayReceiver::HandleRead, this));
    NS_LOG_INFO("Receiver listening on port " << m_port);
}

void
VariableDelayReceiver::StopApplication()
{
    if (m_socket)
    {
        m_socket->Close();
        m_socket->SetRecvCallback(MakeNullCallback<void, Ptr<Socket>>());
    }
}

void
VariableDelayReceiver::HandleRead(Ptr<Socket> socket)
{
    Ptr<Packet> packet;
    Address from;
    
    while ((packet = socket->RecvFrom(from)))
    {
        if (packet->GetSize() > 0)
        {
            // fire Rx trace - this is the egress timestamp
            m_rxTrace(packet, from);

            // cross-traffic experiment: extract send timestamp and compute
            // real end-to-end delay (propagation + transmission + queuing)
            DelayProbeTag tsTag;
            if (m_delayMonitor && packet->RemovePacketTag(tsTag))
            {
                uint64_t sentNs  = tsTag.GetSentNs();
                uint64_t nowNs   = Simulator::Now().GetNanoSeconds();
                double   delayMs = static_cast<double>(nowNs - sentNs) / 1.0e6;
                m_delayMonitor->RecordDelay(m_received, delayMs);
            }

            NS_LOG_INFO("Received packet #" << m_received
                       << " (" << packet->GetSize() << " bytes)"
                       << " at egress t=" << Simulator::Now().GetSeconds() << "s");

            m_received++;
        }
    }
}

}