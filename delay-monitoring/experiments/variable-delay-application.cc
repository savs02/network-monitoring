#include "variable-delay-application.h"
#include "ns3/log.h"
#include "ns3/socket.h"
#include "ns3/simulator.h"
#include "ns3/packet.h"
#include "ns3/udp-socket-factory.h"
#include "ns3/inet-socket-address.h"

namespace ns3 {

NS_LOG_COMPONENT_DEFINE("VariableDelayApplication");
NS_OBJECT_ENSURE_REGISTERED(VariableDelaySender);

TypeId
VariableDelaySender::GetTypeId()
{
    static TypeId tid = TypeId("ns3::VariableDelaySender")
        .SetParent<Application>()
        .SetGroupName("Applications")
        .AddConstructor<VariableDelaySender>();
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
      m_delayRv(nullptr)
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
VariableDelaySender::StartApplication()
{
    if (!m_socket)
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
VariableDelaySender::ScheduleTransmit(Time dt) // schedules SendPacket() to be called after dt time 
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
    
    double sampledDelay = 0.0;
    if (m_delayRv)
    {
        sampledDelay = m_delayRv->GetValue();
        if (sampledDelay < 0) sampledDelay = 0;
    }
    
    NS_LOG_INFO("Packet " << m_packetsSent << ": sampled delay = " << sampledDelay << " ms");
    
    Ptr<Packet> packet = Create<Packet>(m_packetSize);
    
    Time delayTime = MilliSeconds(sampledDelay);
    uint32_t currentPacket = m_packetsSent;
    
    Simulator::Schedule(delayTime, [this, packet, currentPacket]() {
        int sent = m_socket->Send(packet);
        if (sent > 0)
        {
            NS_LOG_INFO("Packet " << currentPacket << " sent at t=" << Simulator::Now().GetSeconds() << "s");
        }
        else
        {
            NS_LOG_ERROR("Failed to send packet " << currentPacket);
        }
    });
    
    m_packetsSent++;
    
    if (m_packetsSent < m_maxPackets)
    {
        ScheduleTransmit(m_interval);
    }
}

NS_OBJECT_ENSURE_REGISTERED(VariableDelayReceiver);

TypeId
VariableDelayReceiver::GetTypeId()
{
    static TypeId tid = TypeId("ns3::VariableDelayReceiver")
        .SetParent<Application>()
        .SetGroupName("Applications")
        .AddConstructor<VariableDelayReceiver>();
    return tid;
}

VariableDelayReceiver::VariableDelayReceiver()
    : m_socket(nullptr),
      m_port(9),
      m_received(0)
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
            NS_LOG_INFO("Received packet #" << m_received 
                       << " (" << packet->GetSize() << " bytes)"
                       << " at t=" << Simulator::Now().GetSeconds() << "s");
            m_received++;
        }
    }
}

}