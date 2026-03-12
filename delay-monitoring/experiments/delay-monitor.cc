#include "delay-monitor.h"
#include <fstream>
#include <iostream>

namespace ns3 {

void
DelayMonitor::RecordDelay(uint32_t seqNum, double delayMs)
{
    m_samples.push_back({seqNum, delayMs});
}

void
DelayMonitor::ExportToCSV(const std::string& filename) const
{
    std::ofstream out(filename);
    if (!out.is_open())
    {
        std::cerr << "DelayMonitor: could not open " << filename << " for writing\n";
        return;
    }

    out << "seq_num,delay_ms\n";
    for (const auto& sample : m_samples)
    {
        out << sample.seqNum << "," << sample.delayMs << "\n";
    }

    out.close();
    std::cout << "DelayMonitor: exported " << m_samples.size()
              << " samples to " << filename << "\n";
}

uint32_t
DelayMonitor::GetSampleCount() const
{
    return static_cast<uint32_t>(m_samples.size());
}

} // namespace ns3
