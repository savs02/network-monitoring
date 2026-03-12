#ifndef VARIABLE_DELAY_APPLICATION_H
#define VARIABLE_DELAY_APPLICATION_H

#include "ns3/application.h"
#include "ns3/socket.h"
#include "ns3/address.h"
#include "ns3/random-variable-stream.h"
#include "ns3/traced-callback.h"
#include "ns3/ipv4-address.h"
#include "delay-monitor.h"

namespace ns3 {

class VariableDelaySender : public Application
{
public:
    static TypeId GetTypeId();
    VariableDelaySender();
    virtual ~VariableDelaySender();
    
    void SetRemote(Ipv4Address ip, uint16_t port);
    void SetDelayRandomVariable(Ptr<RandomVariableStream> delay);
    void SetIntervalRandomVariable(Ptr<RandomVariableStream> interval);
    void SetPacketSize(uint32_t packetSize);
    void SetMaxPackets(uint32_t maxPackets);
    void SetInterval(Time interval);
    void SetDelayMonitor(DelayMonitor* monitor);

protected:
    virtual void DoDispose() override;

private:
    virtual void StartApplication() override;
    virtual void StopApplication() override;
    void ScheduleTransmit(Time dt);
    void SendPacket();
    
    Ptr<Socket> m_socket;
    Ipv4Address m_peerAddress;
    uint16_t m_peerPort;
    uint32_t m_packetSize;
    uint32_t m_maxPackets;
    uint32_t m_packetsSent;
    Time m_interval;
    EventId m_sendEvent;
    Ptr<RandomVariableStream> m_delayRv;
    Ptr<RandomVariableStream> m_intervalRv;
    DelayMonitor* m_delayMonitor; // nullable: only records if set
    
    // trace source for transmitted packets
    TracedCallback<Ptr<const Packet>, const Address&> m_txTrace;
};

class VariableDelayReceiver : public Application
{
public:
    static TypeId GetTypeId();
    VariableDelayReceiver();
    virtual ~VariableDelayReceiver();
    
    void SetPort(uint16_t port);
    uint32_t GetReceived() const;

protected:
    virtual void DoDispose() override;

private:
    virtual void StartApplication() override;
    virtual void StopApplication() override;
    void HandleRead(Ptr<Socket> socket);
    
    Ptr<Socket> m_socket;
    uint16_t m_port;
    uint32_t m_received;
    
    // trace source for received packets
    TracedCallback<Ptr<const Packet>, const Address&> m_rxTrace;
};

} 

#endif