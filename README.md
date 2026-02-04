# network-monitoring

To run the underlying network:

```
# Go to NS-3 directory
cd ~/network-monitoring/ns-3.46

# 1. LogNormal
./ns3 run "single-hop-underlying-network --delayDist=lognormal --lognormal_mu=2.3 --lognormal_sigma=0.2 --numPackets=1000" > ../delay-monitoring/underlying_network_data/lognormal_output.log 2>&1

# 2. Weibull
./ns3 run "single-hop-underlying-network --delayDist=weibull --weibull_scale=10 --weibull_shape=2.5 --numPackets=1000" > ../delay-monitoring/underlying_network_data/weibull_output.log 2>&1

# 3. Normal
./ns3 run "single-hop-underlying-network --delayDist=normal --normal_mean=10 --normal_variance=4 --numPackets=1000" > ../delay-monitoring/underlying_network_data/normal_output.log 2>&1

# Analyze all three
cd ../delay-monitoring/analysis

python3 extract_underlying_delays.py ../underlying_network_data/lognormal_output.log lognormal
python3 extract_underlying_delays.py ../underlying_network_data/weibull_output.log weibull
python3 extract_underlying_delays.py ../underlying_network_data/normal_output.log normal

ls -lh ../underlying_network_data/
```