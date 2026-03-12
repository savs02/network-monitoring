#include "binning-monitor.h"
#include "ns3/log.h"
#include "ns3/simulator.h"
#include <cmath>
#include <limits>

namespace ns3 {

NS_LOG_COMPONENT_DEFINE("BinningMonitor");

BinningMonitor::BinningMonitor(double binWidthMs, bool isShifted)
    : m_binWidthMs(binWidthMs),
      m_isShifted(isShifted),
      m_startTime(isShifted ? binWidthMs / 2.0 : 0.0) // shifted bins start at T/2
{
}

BinningMonitor::~BinningMonitor()
{
}

uint32_t
BinningMonitor::GetBinIndex(Time timestamp) const
{
    double timeMs = timestamp.GetMilliSeconds();
    double adjustedTime = timeMs - m_startTime;
    
    // packets before our bins start don't belong to any bin
    // this happens for shifted bins when packets arrive before T/2
    if (adjustedTime < 0)
    {
        return UINT32_MAX; // special invalid marker
    }
    
    // bin index = floor(adjusted_time / bin_width)
    // e.g., with binWidth=10: time 23ms → bin 2, time 9ms → bin 0
    return static_cast<uint32_t>(std::floor(adjustedTime / m_binWidthMs));
}

void
BinningMonitor::RecordPacket(Time timestamp)
{
    uint32_t binIndex = GetBinIndex(timestamp);
    
    // don't record packets that fall before our bins start
    // shifted bins will skip early packets (before T/2)
    if (binIndex == UINT32_MAX)
    {
        NS_LOG_DEBUG("Packet at t=" << timestamp.GetMilliSeconds() 
                    << "ms is before " << (m_isShifted ? "shifted" : "aligned") 
                    << " bins start (startTime=" << m_startTime << "ms) - not recorded");
        return;
    }
    
    // dynamically expand bin vector as needed
    // we don't know in advance how many bins we'll need
    if (binIndex >= m_binCounts.size())
    {
        m_binCounts.resize(binIndex + 1, 0);
    }
    
    // increment the counter for this bin
    m_binCounts[binIndex]++;
    
    NS_LOG_DEBUG("Recorded packet at t=" << timestamp.GetMilliSeconds() 
                << "ms in bin " << binIndex 
                << " (shifted=" << m_isShifted << ")");
}

void
BinningMonitor::PrintBinCounts() const
{
    NS_LOG_INFO((m_isShifted ? "Shifted" : "Aligned") << " bins (width=" << m_binWidthMs << "ms):");
    
    uint32_t totalPackets = 0;
    for (size_t i = 0; i < m_binCounts.size(); i++)
    {
        // calculate the time range this bin covers
        double binStart = m_startTime + i * m_binWidthMs;
        double binEnd = binStart + m_binWidthMs;
        totalPackets += m_binCounts[i];
        NS_LOG_INFO("  Bin " << i << " [" << binStart << "-" << binEnd << "ms]: " 
                   << m_binCounts[i] << " packets");
    }
    NS_LOG_INFO("  Total packets recorded: " << totalPackets);
}

void
BinningMonitor::ExportToFile(const std::string& filename) const
{
    std::ofstream out(filename);
    out << "bin_index,bin_start_ms,bin_end_ms,packet_count\n";
    
    for (size_t i = 0; i < m_binCounts.size(); i++)
    {
        double binStart = m_startTime + i * m_binWidthMs;
        double binEnd = binStart + m_binWidthMs;
        out << i << "," << binStart << "," << binEnd << "," << m_binCounts[i] << "\n";
    }
    
    out.close();
}

DoubleTimeBinMonitor::DoubleTimeBinMonitor(double binWidthMs)
    : m_binWidthMs(binWidthMs)
{
    // create two monitors: one aligned at 0, one shifted by half bin width
    // aligned catches packets in [0,T], [T,2T], [2T,3T]
    // shifted catches packets in [T/2,3T/2], [3T/2,5T/2]
    // this helps detect packets near bin boundaries
    m_alignedBins = new BinningMonitor(binWidthMs, false);
    m_shiftedBins = new BinningMonitor(binWidthMs, true);
    
    NS_LOG_INFO("Created double time-bin monitor with bin width=" << binWidthMs << "ms");
    NS_LOG_INFO("  Aligned bins start at t=0ms");
    NS_LOG_INFO("  Shifted bins start at t=" << (binWidthMs/2.0) << "ms");
}

DoubleTimeBinMonitor::~DoubleTimeBinMonitor()
{
    delete m_alignedBins;
    delete m_shiftedBins;
}

void
DoubleTimeBinMonitor::RecordPacket(Time timestamp)
{
    // record same packet in both bin sets
    // each monitor decides independently if packet is in range
    // aligned will record all packets from t=0
    // shifted will skip packets before t=binWidth/2
    m_alignedBins->RecordPacket(timestamp);
    m_shiftedBins->RecordPacket(timestamp);
}

void
DoubleTimeBinMonitor::PrintSummary() const
{
    NS_LOG_INFO("=== Double Time-Bin Monitor Summary ===");
    m_alignedBins->PrintBinCounts();
    NS_LOG_INFO("");
    m_shiftedBins->PrintBinCounts();
}

void
DoubleTimeBinMonitor::ExportToFile(const std::string& filename) const
{
    // export to two separate CSV files for analysis
    std::string alignedFile = filename + "_aligned.csv";
    std::string shiftedFile = filename + "_shifted.csv";
    
    m_alignedBins->ExportToFile(alignedFile);
    m_shiftedBins->ExportToFile(shiftedFile);
    
    NS_LOG_INFO("Exported bin counts to " << alignedFile << " and " << shiftedFile);
}

}