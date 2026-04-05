#ifndef DELAY_MONITOR_H
#define DELAY_MONITOR_H

#include <vector>
#include <string>
#include <cstdint>

namespace ns3 {

// Collects per-packet delay samples recorded directly by the sender and exports them to CSV.
// Each sample is the value drawn from the underlying delay distribution for that packet.
// This is the baseline (non-binning) monitoring approach: exact samples, no aggregation.
class DelayMonitor
{
public:
    // record the sampled delay for a given packet sequence number
    void RecordDelay(uint32_t seqNum, double delayMs);

    void ExportToCSV(const std::string& filename) const;

    uint32_t GetSampleCount() const;

private:
    struct DelaySample
    {
        uint32_t seqNum;
        double delayMs;
    };

    std::vector<DelaySample> m_samples;
};

} // namespace ns3

#endif
