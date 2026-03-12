#ifndef BINNING_MONITOR_H
#define BINNING_MONITOR_H

#include "ns3/nstime.h"
#include <vector>
#include <fstream>
#include <string>

namespace ns3 {

// represents a single set of time bins (either aligned or shifted)
// bins partition time into fixed-width intervals and count packets in each
class BinningMonitor
{
public:
    BinningMonitor(double binWidthMs, bool isShifted = false);
    ~BinningMonitor();
    
    void RecordPacket(Time timestamp);
    void PrintBinCounts() const;
    void ExportToFile(const std::string& filename) const;
    
    std::vector<uint32_t> GetBinCounts() const { return m_binCounts; }
    double GetBinWidth() const { return m_binWidthMs; }
    bool IsShifted() const { return m_isShifted; }
    
private:
    // calculates which bin index a timestamp falls into
    // returns UINT32_MAX if timestamp is before bins start
    uint32_t GetBinIndex(Time timestamp) const;
    
    double m_binWidthMs;
    bool m_isShifted;
    double m_startTime; // 0 for aligned, binWidthMs/2 for shifted
    std::vector<uint32_t> m_binCounts; // packet count for each bin
};

// manages two BinningMonitor objects: one aligned, one shifted
// this implements the double time-binning mechanism for boundary detection
class DoubleTimeBinMonitor
{
public:
    DoubleTimeBinMonitor(double binWidthMs);
    ~DoubleTimeBinMonitor();
    
    void RecordPacket(Time timestamp);
    void PrintSummary() const;
    void ExportToFile(const std::string& filename) const;
    
    BinningMonitor* GetAlignedMonitor() { return m_alignedBins; }
    BinningMonitor* GetShiftedMonitor() { return m_shiftedBins; }
    
private:
    double m_binWidthMs;
    BinningMonitor* m_alignedBins;  // bins at [0,T], [T,2T], [2T,3T] etc
    BinningMonitor* m_shiftedBins;  // bins at [T/2,3T/2], [3T/2,5T/2] etc
};

} 

#endif