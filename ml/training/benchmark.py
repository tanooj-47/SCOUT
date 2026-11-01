"""
ml/training/benchmark.py - Nondestructive CPU resource, memory, and throughput profiling harness.
"""

import copy
import gc
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import psutil
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from ml.config import NUM_CLASSES
from ml.training.config import BenchmarkConfig


class InsufficientMemoryError(Exception):
    """Raised when available system RAM fails the preflight memory reserve check."""


class BenchmarkEmergencyAbortError(Exception):
    """Raised when system available memory falls below the critical emergency floor during benchmarking."""


class CPUBenchmark:
    """
    Nondestructive CPU performance profiler measuring compute latency, data loading time,
    and process memory dynamics across thread allocations and batch sizes.

    Safety Guarantees:
        - Never mutates real model weights or training DataLoader sequences.
        - Preflight check: Refuses to execute if available RAM is below the safety reserve.
        - Whole-run emergency abort: Immediately halts entire benchmark if available RAM
          crosses the emergency floor. Never moves on to the next configuration.
        - State restoration: Restores original thread counts and RNG states in a guaranteed finally block.
        - Documents that sampled RSS reflects resident working set rather than instantaneous C++ ATen peak.
    """

    def __init__(self, config: Optional[BenchmarkConfig] = None) -> None:
        self.config = config or BenchmarkConfig()
        self.process = psutil.Process(os.getpid())

    def create_synthetic_benchmark_loader(
        self,
        batch_size: int,
        num_batches: int,
        generator: torch.Generator,
    ) -> DataLoader:
        """Creates an isolated synthetic DataLoader for profiling."""
        total_samples = batch_size * num_batches
        dummy_x = torch.randn(total_samples, 3, 224, 224, dtype=torch.float32)
        dummy_y = torch.randint(0, NUM_CLASSES, (total_samples,), dtype=torch.long)
        dataset = TensorDataset(dummy_x, dummy_y)
        return DataLoader(
            dataset,
            batch_size=batch_size,
            shuffle=True,
            generator=generator,
            num_workers=0,
        )

    def run(
        self,
        model: nn.Module,
        model_name: str = "model",
    ) -> Dict[str, Any]:
        """
        Executes the benchmark matrix across configured thread counts and batch sizes.

        Args:
            model: PyTorch model architecture to benchmark (isolated disposable copy is made).
            model_name: Identifier for logging.

        Returns:
            Dictionary containing benchmark results and recommendations.
        """
        # 1. Preflight System Memory Check
        current_available_ram = psutil.virtual_memory().available
        if current_available_ram < self.config.min_available_ram_bytes:
            raise InsufficientMemoryError(
                f"Preflight memory check failed: Available system RAM is "
                f"{current_available_ram / (1024**2):.1f} MB, which is below the safe "
                f"reserve of {self.config.min_available_ram_bytes / (1024**2):.1f} MB. "
                f"Benchmarking cannot safely proceed under current system memory pressure."
            )

        # 2. Preserve Global State for Guaranteed Restoration
        orig_threads = torch.get_num_threads()
        orig_torch_rng = torch.get_rng_state()
        orig_py_rng = random.getstate()
        orig_np_rng = np.random.get_state()

        results: List[Dict[str, Any]] = []

        try:
            for threads in self.config.thread_counts:
                torch.set_num_threads(threads)

                for batch_size in self.config.batch_sizes:
                    # Record per-configuration baseline
                    rss_base = self.process.memory_info().rss
                    ram_avail_base = psutil.virtual_memory().available

                    # Disposable model clone and optimizer
                    disposable_model = copy.deepcopy(model).train()
                    disposable_optimizer = torch.optim.AdamW(
                        [p for p in disposable_model.parameters() if p.requires_grad],
                        lr=1e-3,
                    )
                    criterion = nn.CrossEntropyLoss()

                    # Isolated benchmark loader and dedicated generator
                    bench_gen = torch.Generator().manual_seed(9999)
                    total_batches = self.config.warmup_batches + self.config.measured_batches
                    bench_loader = self.create_synthetic_benchmark_loader(
                        batch_size=batch_size,
                        num_batches=total_batches,
                        generator=bench_gen,
                    )

                    peak_rss = rss_base
                    min_avail_ram = ram_avail_base
                    data_times: List[float] = []
                    compute_times: List[float] = []

                    loader_iter = iter(bench_loader)

                    # 3. Warm-up Batches (2 batches)
                    for _ in range(self.config.warmup_batches):
                        # Emergency memory floor check
                        avail_now = psutil.virtual_memory().available
                        min_avail_ram = min(min_avail_ram, avail_now)
                        if avail_now < self.config.emergency_memory_floor_bytes:
                            raise BenchmarkEmergencyAbortError(
                                f"EMERGENCY BENCHMARK ABORT: Available system RAM dropped to "
                                f"{avail_now / (1024**2):.1f} MB during warm-up (floor: "
                                f"{self.config.emergency_memory_floor_bytes / (1024**2):.1f} MB). "
                                f"Aborting entire benchmark run to prevent process/system OOM."
                            )

                        images, targets = next(loader_iter)
                        disposable_optimizer.zero_grad()
                        logits = disposable_model(images)
                        loss = criterion(logits, targets)
                        loss.backward()
                        disposable_optimizer.step()

                    # 4. Measured Batches (10 batches)
                    for _ in range(self.config.measured_batches):
                        # Measure data retrieval latency
                        t_data_start = time.perf_counter()
                        images, targets = next(loader_iter)
                        t_data_end = time.perf_counter()
                        data_times.append(t_data_end - t_data_start)

                        # Check memory before compute
                        avail_now = psutil.virtual_memory().available
                        min_avail_ram = min(min_avail_ram, avail_now)
                        if avail_now < self.config.emergency_memory_floor_bytes:
                            raise BenchmarkEmergencyAbortError(
                                f"EMERGENCY BENCHMARK ABORT: Available system RAM dropped to "
                                f"{avail_now / (1024**2):.1f} MB during measurement (floor: "
                                f"{self.config.emergency_memory_floor_bytes / (1024**2):.1f} MB). "
                                f"Aborting entire benchmark run to prevent process/system OOM."
                            )

                        # Measure computation latency
                        t_comp_start = time.perf_counter()
                        disposable_optimizer.zero_grad()
                        logits = disposable_model(images)
                        loss = criterion(logits, targets)
                        loss.backward()
                        disposable_optimizer.step()
                        t_comp_end = time.perf_counter()
                        compute_times.append(t_comp_end - t_comp_start)

                        # Sample process RSS after computation
                        current_rss = self.process.memory_info().rss
                        peak_rss = max(peak_rss, current_rss)

                    # Calculate summary metrics for this configuration
                    mean_data_sec = float(np.mean(data_times))
                    mean_comp_sec = float(np.mean(compute_times))
                    mean_step_sec = mean_data_sec + mean_comp_sec
                    images_per_sec = float(batch_size / mean_step_sec) if mean_step_sec > 0 else 0.0
                    delta_rss = peak_rss - rss_base

                    results.append({
                        "threads": threads,
                        "batch_size": batch_size,
                        "images_per_sec": round(images_per_sec, 2),
                        "mean_data_ms": round(mean_data_sec * 1000, 2),
                        "mean_compute_ms": round(mean_comp_sec * 1000, 2),
                        "mean_step_ms": round(mean_step_sec * 1000, 2),
                        "baseline_rss_mb": round(rss_base / (1024**2), 2),
                        "peak_rss_mb": round(peak_rss / (1024**2), 2),
                        "delta_rss_mb": round(delta_rss / (1024**2), 2),
                        "min_available_ram_mb": round(min_avail_ram / (1024**2), 2),
                        "status": "PASSED",
                    })

                    # Clean up disposable references
                    del disposable_model, disposable_optimizer, bench_loader
                    gc.collect()

        finally:
            # Guaranteed restoration of original environment state
            torch.set_num_threads(orig_threads)
            torch.set_rng_state(orig_torch_rng)
            random.setstate(orig_py_rng)
            np.random.set_state(orig_np_rng)
            gc.collect()

        # Recommendation logic based on measured evidence
        recommendation = self.recommend_configuration(results)

        return {
            "model_name": model_name,
            "results": results,
            "recommendation": recommendation,
            "sampled_rss_note": (
                "Notice: Sampled RSS reflects the process working set queried periodically via psutil. "
                "True instantaneous peak memory within native C++ ATen allocators may be higher. "
                "Sampled RSS represents an empirical lower bound."
            ),
        }

    def recommend_configuration(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Finds highest throughput configuration that maintained safe memory margins."""
        safe_configs = [
            r for r in results
            if r["status"] == "PASSED" and r["min_available_ram_mb"] >= 450.0
        ]
        if not safe_configs:
            # If none maintained 450 MB, select the one with highest minimum available RAM
            safest = max(results, key=lambda x: x["min_available_ram_mb"])
            return {
                "recommended_threads": safest["threads"],
                "recommended_batch_size": safest["batch_size"],
                "throughput_ips": safest["images_per_sec"],
                "warning": (
                    "High memory pressure observed across all configurations. Recommend freeing "
                    "system memory before initiating prolonged training."
                ),
            }

        # Select configuration with maximum throughput among safe ones
        best = max(safe_configs, key=lambda x: x["images_per_sec"])
        return {
            "recommended_threads": best["threads"],
            "recommended_batch_size": best["batch_size"],
            "throughput_ips": best["images_per_sec"],
            "warning": None,
        }
