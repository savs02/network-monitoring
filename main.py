import networkx as nx
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation


class NetworkModel:
    def __init__(self, seed=42):
        np.random.seed(seed)
        self.G = nx.Graph()
        self.edges = [("S", "A"), ("S", "B"), ("A", "B"), ("A", "D"), ("B", "D")]
        self.G.add_edges_from(self.edges)
        self.link_delays = self._init_link_delays()

    def _init_link_delays(self):
        delays = {}
        for u, v in self.G.edges:
            mean = np.random.uniform(5, 20)
            std = np.random.uniform(1, 5)
            delays[(u, v)] = (mean, std)
        return delays

    def get_link_params(self, u, v):
        if (u, v) in self.link_delays:
            return self.link_delays[(u, v)]
        elif (v, u) in self.link_delays:
            return self.link_delays[(v, u)]
        else:
            raise KeyError(f"Edge ({u}, {v}) not found")

    def print_link_info(self):
        print("=== Link delay distributions (mean ± std) ===")
        for (u, v), (mean, std) in self.link_delays.items():
            print(f"{u}-{v}: {mean:.2f} ± {std:.2f}")



class NetworkSimulation:
    def __init__(self, model: NetworkModel):
        self.model = model
        self.paths = {
            "P1": ["S", "A", "D"],
            "P2": ["S", "B", "D"],
            "P3": ["S", "A", "B", "D"],
            "P4": ["S", "B", "A", "D"],
        }

    def simulate_path_delay(self, path, n_samples=100000):
        total_delays = np.zeros(n_samples)
        for i in range(len(path) - 1):
            mean, std = self.model.get_link_params(path[i], path[i + 1])
            total_delays += np.random.normal(mean, std, n_samples)
        return total_delays

    def run_baseline(self, n_samples=100000):
        """Simulate all paths under normal conditions."""
        return {p: self.simulate_path_delay(nodes, n_samples) for p, nodes in self.paths.items()}


    def simulate_with_load(self, path, load_factor, n_samples=50000):
        total_delays = np.zeros(n_samples)
        for i in range(len(path) - 1):
            mean, std = self.model.get_link_params(path[i], path[i + 1])
            if path[i] == "S" or path[i + 1] == "S":
                mean *= (1 + 0.8 * load_factor)
                std *= (1 + 0.5 * load_factor)
            else:
                mean *= (1 + 0.2 * load_factor)
                std *= (1 + 0.1 * load_factor)
            total_delays += np.random.normal(mean, std, n_samples)
        return total_delays

    def run_load_balancer_case(self, load_levels=np.linspace(0, 1.0, 10), n_samples=50000):
        results = []
        for load in load_levels:
            delays = {p: self.simulate_with_load(nodes, load, n_samples) for p, nodes in self.paths.items()}
            results.append((load, delays))
        return results


    def simulate_failure_reroute_to_p1(self, n_samples=80000, heal=True):

        results = []

        delays_baseline = {p: self.simulate_path_delay(nodes, n_samples) for p, nodes in self.paths.items()}
        results.append(("Baseline (all paths active)", delays_baseline))

        delays_failure = {"P1": self.simulate_path_delay(["S", "B", "D"], n_samples)}
        results.append(("Failure (A down → all rerouted via P1)", delays_failure))

        if heal:
            delays_heal = {p: self.simulate_path_delay(nodes, n_samples) for p, nodes in self.paths.items()}
            results.append(("Healing / Rebalancing (A restored)", delays_heal))

        return results

class NetworkVisualizer:
    def plot_histograms(self, path_delays, title="Baseline Delay Distributions"):
        plt.figure(figsize=(10, 6))
        for p, delays in path_delays.items():
            plt.hist(delays, bins=100, alpha=0.5, density=True,
                     label=f"{p} (μ={delays.mean():.1f}, σ={delays.std():.1f})")
        plt.title(title)
        plt.xlabel("Total Delay (time units)")
        plt.ylabel("Probability Density")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.show()

    def animate_load_case(self, load_results):
        fig, ax = plt.subplots(figsize=(10, 6))
        bins = np.linspace(0, 100, 100)

        def update(frame):
            ax.clear()
            load, delays_dict = load_results[frame]
            for p, delays in delays_dict.items():
                ax.hist(delays, bins=bins, alpha=0.5, density=True, label=f"{p}")
            ax.set_title(f"Use Case 5: Load Balancer at S (Load = {load:.2f})")
            ax.set_xlabel("Total Delay (time units)")
            ax.set_ylabel("Probability Density")
            ax.legend()
            ax.grid(True)

        ani = FuncAnimation(fig, update, frames=len(load_results), interval=800, repeat=True)
        plt.show()
        return ani  

    def animate_failure_reroute(self, reroute_results):
        fig, ax = plt.subplots(figsize=(10, 6))
        bins = np.linspace(0, 100, 100)

        def update(frame):
            ax.clear()
            stage, delays_dict = reroute_results[frame]
            for p, delays in delays_dict.items():
                ax.hist(delays, bins=bins, alpha=0.5, density=True, label=f"{p}")
            ax.set_title(f"Use Case 4: {stage}")
            ax.set_xlabel("Total Delay (time units)")
            ax.set_ylabel("Probability Density")
            ax.legend()
            ax.grid(True)

        ani = FuncAnimation(fig, update, frames=len(reroute_results), interval=1500, repeat=True)
        plt.show()
        return ani


if __name__ == "__main__":
    model = NetworkModel()
    model.print_link_info()

    sim = NetworkSimulation(model)
    vis = NetworkVisualizer()

    baseline_delays = sim.run_baseline()
    vis.plot_histograms(baseline_delays, title="Baseline (Normal) Delay Distributions")

    load_results = sim.run_load_balancer_case()
    ani_load = vis.animate_load_case(load_results)

    reroute_results = sim.simulate_failure_reroute_to_p1(heal=True)
    ani_fail = vis.animate_failure_reroute(reroute_results)
