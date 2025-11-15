#!/usr/bin/env python3
# filepath: /home/miksolo/git/CerebroV1_real_time_visualizer/scripts/dataset_report_generator.py

"""
Neural Dataset Report Generator

This script generates comprehensive EDA reports from neural spike dataset JSON files.
It creates visualizations and statistical summaries in PDF format.

Usage:
    python dataset_report_generator.py --input path/to/data.json --output report.pdf
    python dataset_report_generator.py -i data.json  # Uses default output name
    python dataset_report_generator.py  # Uses default input and output
"""

import json
import argparse
import os
from datetime import datetime
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER

VOLTAGE_THRESHOLD_MAX = 2.1  # Voltage threshold to filter cycles
VOLTAGE_THRESHOLD_MIN = 0.0

def get_dataset(dataset_path):
    """Load a single dataset from a JSON file."""
    with open(dataset_path, 'r') as f:
        neural_data = json.load(f)
    non_zero_gt_count = 0
    doubles_count = 0
    
    dataset = []
    for i, message in enumerate(neural_data['messages']):
        cycles = message['data']['cycles']
        for cycle in cycles:
            if cycle.get('gt') and len(cycle['gt']) > 0 and float(cycle['v']) < VOLTAGE_THRESHOLD_MAX and float(cycle['v']) > VOLTAGE_THRESHOLD_MIN:
                non_zero_gt_count += 1
                dataset.append(cycle)
                if len(cycle['gt']) > 1:
                    doubles_count += 1
    
    print(f"  Loaded {len(dataset)} cycles from {dataset_path}")
    print(f"  Non-zero ground truth count: {non_zero_gt_count}")
    print(f"  Doubles count: {doubles_count}")
    return dataset


def get_combined_dataset(dataset_paths):
    """
    Load and combine multiple datasets from JSON files.
    
    Args:
        dataset_paths: List of paths to JSON dataset files
        
    Returns:
        Combined dataset list
    """
    if isinstance(dataset_paths, str):
        dataset_paths = [dataset_paths]
    
    print(f"\nLoading {len(dataset_paths)} dataset file(s)...")
    combined_dataset = []
    
    for path in dataset_paths:
        print(f"\nProcessing: {path}")
        dataset = get_dataset(path)
        combined_dataset.extend(dataset)
    
    print(f"\n{'='*60}")
    print(f"Combined dataset size: {len(combined_dataset)} cycles")
    print(f"{'='*60}\n")
    
    return combined_dataset


class DatasetExplorer:
    """
    Exploratory Data Analysis for capacitor discharge dataset.
    Now includes visualization for multi-spike cycles.
    """
    
    def __init__(self, v_initial_guess: float = 2.5):
        """
        Args:
            v_initial_guess: Estimated initial voltage for reference
        """
        self.v_initial_guess = v_initial_guess
        self.data = None
        
    def load_and_parse_data(self, dataset_path) -> Dict:
        """
        Load dataset and extract relevant features.
        
        Args:
            dataset_path: Single path or list of paths to dataset file(s)
        
        Returns:
            Dictionary with parsed data
        """
        # Support both single path and list of paths
        if isinstance(dataset_path, str):
            dataset = get_dataset(dataset_path)
        else:
            dataset = get_combined_dataset(dataset_path)
        
        v_currents = []
        gt_times = []
        cycle_lengths = []
        num_spikes = []
        valid_indices = []
        invalid_reasons = []
        has_multiple_spikes = []  # NEW: Track if cycle had multiple spikes
        
        for idx, exp_data in enumerate(dataset):
            v_current = float(exp_data["v"])
            t_cycle = exp_data["t"]
            cycle_lengths.append(t_cycle)
            spike_count = len(exp_data["gt"])
            num_spikes.append(spike_count)
            
            # Check if valid data point
            if not exp_data["gt"]:
                invalid_reasons.append((idx, "no_spikes", v_current, None))
                continue
            
            gt_time_us = t_cycle - exp_data["gt"][-1]
            
            # Track invalid data
            if gt_time_us <= 0:
                invalid_reasons.append((idx, "negative_time", v_current, gt_time_us))
                continue
            if v_current >= self.v_initial_guess:
                invalid_reasons.append((idx, "v_too_high", v_current, gt_time_us))
                continue
            if v_current <= 0:
                invalid_reasons.append((idx, "v_negative", v_current, gt_time_us))
                continue
            
            # Valid data
            v_currents.append(v_current)
            gt_times.append(gt_time_us)
            valid_indices.append(idx)
            has_multiple_spikes.append(spike_count > 1)  # NEW: Track if multiple spikes
        
        self.data = {
            'v_currents': np.array(v_currents),
            'gt_times': np.array(gt_times),
            'cycle_lengths': np.array(cycle_lengths),
            'num_spikes': np.array(num_spikes),
            'valid_indices': valid_indices,
            'invalid_reasons': invalid_reasons,
            'has_multiple_spikes': np.array(has_multiple_spikes),  # NEW
            'total_samples': len(dataset),
            'valid_samples': len(v_currents)
        }
        
        return self.data
    
    def print_summary_statistics(self):
        """Print comprehensive dataset statistics."""
        if self.data is None:
            print("No data loaded. Call load_and_parse_data() first.")
            return
        
        print("\n" + "="*70)
        print(" "*20 + "DATASET SUMMARY STATISTICS")
        print("="*70)
        
        print(f"\n{'Total Samples:':<30} {self.data['total_samples']}")
        print(f"{'Valid Samples:':<30} {self.data['valid_samples']}")
        print(f"{'Invalid Samples:':<30} {self.data['total_samples'] - self.data['valid_samples']}")
        print(f"{'Valid Ratio:':<30} {self.data['valid_samples']/self.data['total_samples']*100:.2f}%")
        
        # NEW: Multi-spike statistics
        multi_spike_count = self.data['has_multiple_spikes'].sum()
        single_spike_count = (~self.data['has_multiple_spikes']).sum()
        print(f"\n{'Single Spike Cycles:':<30} {single_spike_count} ({single_spike_count/self.data['valid_samples']*100:.1f}%)")
        print(f"{'Multi-Spike Cycles:':<30} {multi_spike_count} ({multi_spike_count/self.data['valid_samples']*100:.1f}%)")
        
        # Invalid data breakdown
        if self.data['invalid_reasons']:
            print(f"\n{'Invalid Data Breakdown:':}")
            reasons_count = {}
            for _, reason, _, _ in self.data['invalid_reasons']:
                reasons_count[reason] = reasons_count.get(reason, 0) + 1
            for reason, count in reasons_count.items():
                print(f"  - {reason:<20} {count:>5} samples")
        
        print("\n" + "-"*70)
        print(" "*25 + "VOLTAGE STATISTICS")
        print("-"*70)
        v = self.data['v_currents']
        print(f"{'Min Voltage:':<30} {v.min():.6f} V")
        print(f"{'Max Voltage:':<30} {v.max():.6f} V")
        print(f"{'Mean Voltage:':<30} {v.mean():.6f} V")
        print(f"{'Median Voltage:':<30} {np.median(v):.6f} V")
        print(f"{'Std Voltage:':<30} {v.std():.6f} V")
        print(f"{'Voltage Range:':<30} {v.max() - v.min():.6f} V")
        
        # NEW: Compare voltage between single and multi-spike cycles
        single_spike_v = v[~self.data['has_multiple_spikes']]
        multi_spike_v = v[self.data['has_multiple_spikes']]
        if len(multi_spike_v) > 0:
            print(f"\n{'Single-Spike Mean V:':<30} {single_spike_v.mean():.6f} V")
            print(f"{'Multi-Spike Mean V:':<30} {multi_spike_v.mean():.6f} V")
            print(f"{'Voltage Difference:':<30} {abs(multi_spike_v.mean() - single_spike_v.mean()):.6f} V")
        
        print("\n" + "-"*70)
        print(" "*25 + "SPIKE TIME STATISTICS")
        print("-"*70)
        t = self.data['gt_times']
        print(f"{'Min Time:':<30} {t.min():.2f} μs")
        print(f"{'Max Time:':<30} {t.max():.2f} μs")
        print(f"{'Mean Time:':<30} {t.mean():.2f} μs")
        print(f"{'Median Time:':<30} {np.median(t):.2f} μs")
        print(f"{'Std Time:':<30} {t.std():.2f} μs")
        print(f"{'Time Range:':<30} {t.max() - t.min():.2f} μs")
        
        print("\n" + "-"*70)
        print(" "*25 + "CYCLE STATISTICS")
        print("-"*70)
        c = self.data['cycle_lengths']
        print(f"{'Mean Cycle Length:':<30} {c.mean():.2f} μs")
        print(f"{'Median Cycle Length:':<30} {np.median(c):.2f} μs")
        print(f"{'Max Cycle Length:':<30} {c.max():.2f} μs")
        print(f"{'Min Cycle Length:':<30} {c.min():.2f} μs")
        
        print("\n" + "-"*70)
        print(" "*25 + "SPIKE STATISTICS")
        print("-"*70)
        s = self.data['num_spikes']
        print(f"{'Mean Spikes per Cycle:':<30} {s.mean():.2f}")
        print(f"{'Max Spikes in Cycle:':<30} {s.max()}")
        print(f"{'Min Spikes in Cycle:':<30} {s.min()}")
        
        print("\n" + "="*70 + "\n")
    
    def plot_comprehensive_eda(self, save_path: str = None, dataset_path: str = ""):
        """
        Create comprehensive EDA visualizations.
        Multi-spike cycles are colored RED, single-spike cycles are colored BLUE.
        """
        if self.data is None:
            print("No data loaded. Call load_and_parse_data() first.")
            return
        
        fig = plt.figure(figsize=(18, 12))
        gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)
        
        v = self.data['v_currents']
        t = self.data['gt_times']
        
        # 1. Voltage vs Time Scatter (Main plot) - NEW: Color-coded by spike count
        ax1 = fig.add_subplot(gs[0:2, 0:2])
        
        # Color based on multiple spikes: RED for multi-spike, BLUE for single-spike
        colors = np.where(self.data['has_multiple_spikes'], '#e74c3c', '#3498db')
        scatter = ax1.scatter(v, t, alpha=0.6, s=35, c=colors, edgecolors='black', linewidths=0.3)
        
        ax1.set_xlabel('Voltage (V)', fontsize=12)
        ax1.set_ylabel('Time Since Last Spike (μs)', fontsize=12)
        ax1.set_title('Voltage vs Time (Color-Coded by Spike Count)', fontsize=14, fontweight='bold')
        ax1.grid(True, alpha=0.3)
        
        # Add v_initial reference line and create comprehensive legend
        ax1.axvline(self.v_initial_guess, color='green', linestyle='--', linewidth=2)
        
        multi_count = self.data['has_multiple_spikes'].sum()
        single_count = (~self.data['has_multiple_spikes']).sum()
        
        legend_elements = [
            Patch(facecolor='#3498db', edgecolor='black', alpha=0.6, 
                  label=f'Single Spike ({single_count}, {single_count/len(v)*100:.1f}%)'),
            Patch(facecolor='#e74c3c', edgecolor='black', alpha=0.6, 
                  label=f'Multiple Spikes ({multi_count}, {multi_count/len(v)*100:.1f}%)'),
            Line2D([0], [0], color='green', linestyle='--', linewidth=2, 
                   label=f'V_initial = {self.v_initial_guess}V')
        ]
        ax1.legend(handles=legend_elements, loc='upper right', fontsize=10)
        
        # 2. Voltage Distribution - NEW: Split by spike count
        ax2 = fig.add_subplot(gs[0, 2])
        v_single = v[~self.data['has_multiple_spikes']]
        v_multi = v[self.data['has_multiple_spikes']]
        
        ax2.hist(v_single, bins=40, alpha=0.6, color='#3498db', edgecolor='black', label='Single')
        if len(v_multi) > 0:
            ax2.hist(v_multi, bins=40, alpha=0.6, color='#e74c3c', edgecolor='black', label='Multi')
        
        ax2.axvline(v.mean(), color='black', linestyle='--', linewidth=2, label='Overall Mean')
        ax2.set_xlabel('Voltage (V)', fontsize=10)
        ax2.set_ylabel('Frequency', fontsize=10)
        ax2.set_title('Voltage Distribution by Spike Count', fontsize=12, fontweight='bold')
        ax2.legend()
        ax2.grid(True, alpha=0.3, axis='y')
        
        # 3. Time Distribution
        ax3 = fig.add_subplot(gs[1, 2])
        ax3.hist(t, bins=50, alpha=0.7, color='coral', edgecolor='black')
        ax3.axvline(t.mean(), color='red', linestyle='--', linewidth=2, label='Mean')
        ax3.axvline(np.median(t), color='orange', linestyle='--', linewidth=2, label='Median')
        ax3.set_xlabel('Time (μs)', fontsize=10)
        ax3.set_ylabel('Frequency', fontsize=10)
        ax3.set_title('Time Distribution', fontsize=12, fontweight='bold')
        ax3.legend()
        ax3.grid(True, alpha=0.3, axis='y')
        
        # 4. Voltage vs Time (Log scale) - NEW: Color-coded
        ax4 = fig.add_subplot(gs[2, 0])
        ax4.scatter(v, t, alpha=0.6, s=20, c=colors, edgecolors='black', linewidths=0.2)
        ax4.set_xlabel('Voltage (V)', fontsize=10)
        ax4.set_ylabel('Time (μs) - Log Scale', fontsize=10)
        ax4.set_yscale('log')
        ax4.set_title('Voltage vs Time (Log Scale)', fontsize=12, fontweight='bold')
        ax4.grid(True, alpha=0.3, which='both')
        
        # 5. Voltage Ratio Distribution - NEW: Split by spike count
        ax5 = fig.add_subplot(gs[2, 1])
        voltage_ratio = v / self.v_initial_guess
        voltage_ratio_single = voltage_ratio[~self.data['has_multiple_spikes']]
        voltage_ratio_multi = voltage_ratio[self.data['has_multiple_spikes']]
        
        ax5.hist(voltage_ratio_single, bins=40, alpha=0.6, color='#3498db', edgecolor='black', label='Single')
        if len(voltage_ratio_multi) > 0:
            ax5.hist(voltage_ratio_multi, bins=40, alpha=0.6, color='#e74c3c', edgecolor='black', label='Multi')
        
        ax5.set_xlabel('Voltage Ratio (V/V_initial)', fontsize=10)
        ax5.set_ylabel('Frequency', fontsize=10)
        ax5.set_title('Voltage Ratio by Spike Count', fontsize=12, fontweight='bold')
        ax5.axvline(voltage_ratio.mean(), color='black', linestyle='--', linewidth=2, label='Mean')
        ax5.legend()
        ax5.grid(True, alpha=0.3, axis='y')
        
        # 6. Spike Count Breakdown
        ax6 = fig.add_subplot(gs[2, 2])
        
        colors_pie = ['#3498db', '#e74c3c']
        labels = [f'Single Spike\n({single_count})', f'Multiple Spikes\n({multi_count})']
        sizes = [single_count, multi_count]
        
        wedges, texts, autotexts = ax6.pie(sizes, labels=labels, colors=colors_pie, 
                                             autopct='%1.1f%%', startangle=90,
                                             textprops={'fontsize': 10})
        ax6.set_title('Spike Count Distribution', fontsize=12, fontweight='bold')
        
        # Make percentage text bold
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
        
        title = 'Comprehensive Dataset Exploration - Multi-Spike Analysis'
        if dataset_path:
            title += f'\nPath: {dataset_path}'
        plt.suptitle(title, fontsize=16, fontweight='bold', y=0.995)
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        # # plt.show()
    
    def plot_multispike_comparison(self, save_path: str = None, dataset_path=None):
        """
        NEW: Dedicated plot to compare cycles with different numbers of spikes (1, 2, 3+).
        
        Args:
            save_path: Path to save the plot
            dataset_path: Path(s) to the dataset file (needed to re-load spike counts)
        """
        if self.data is None:
            print("No data loaded. Call load_and_parse_data() first.")
            return
        
        if dataset_path is None:
            print("Error: dataset_path is required for multispike comparison.")
            return
        
        v = self.data['v_currents']
        t = self.data['gt_times']
        
        # Get indices for each spike count - handle both single and multiple files
        if isinstance(dataset_path, str):
            dataset = get_dataset(dataset_path)
        else:
            dataset = get_combined_dataset(dataset_path)
        
        spike_counts = []
        for idx in self.data['valid_indices']:
            spike_counts.append(len(dataset[idx]['gt']))
        spike_counts = np.array(spike_counts)
        
        # Separate data by spike count
        single_spike_mask = spike_counts == 1
        double_spike_mask = spike_counts == 2
        triple_plus_mask = spike_counts >= 3
        
        v_single = v[single_spike_mask]
        t_single = t[single_spike_mask]
        v_double = v[double_spike_mask]
        t_double = t[double_spike_mask]
        v_triple = v[triple_plus_mask]
        t_triple = t[triple_plus_mask]
        
        print(f"Spike count breakdown:")
        print(f"  Single spike: {len(v_single)} ({len(v_single)/len(v)*100:.1f}%)")
        print(f"  Double spike: {len(v_double)} ({len(v_double)/len(v)*100:.1f}%)")
        print(f"  Triple+ spike: {len(v_triple)} ({len(v_triple)/len(v)*100:.1f}%)")
        
        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        
        # Colors for different spike counts
        colors = ['#3498db', '#e74c3c', '#f39c12']  # Blue, Red, Orange
        labels = ['Single Spike', 'Double Spike', 'Triple+ Spike']
        
        # 1. Overlaid scatter plot
        ax1 = axes[0, 0]
        if len(v_single) > 0:
            ax1.scatter(v_single, t_single, alpha=0.5, s=20, c=colors[0], 
                       label=f'Single ({len(v_single)})', edgecolors='black', linewidths=0.2)
        if len(v_double) > 0:
            ax1.scatter(v_double, t_double, alpha=0.7, s=30, c=colors[1], 
                       label=f'Double ({len(v_double)})', edgecolors='black', linewidths=0.3)
        if len(v_triple) > 0:
            ax1.scatter(v_triple, t_triple, alpha=0.8, s=40, c=colors[2], 
                       label=f'Triple+ ({len(v_triple)})', edgecolors='black', linewidths=0.3)
        
        ax1.set_xlabel('Voltage (V)', fontsize=11)
        ax1.set_ylabel('Time Since Last Spike (μs)', fontsize=11)
        ax1.set_title('Cycles by Spike Count', fontsize=13, fontweight='bold')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 2. Voltage comparison boxplot
        ax2 = axes[0, 1]
        box_data = []
        box_labels = []
        box_colors = []
        
        if len(v_single) > 0:
            box_data.append(v_single)
            box_labels.append('Single')
            box_colors.append(colors[0])
        if len(v_double) > 0:
            box_data.append(v_double)
            box_labels.append('Double')
            box_colors.append(colors[1])
        if len(v_triple) > 0:
            box_data.append(v_triple)
            box_labels.append('Triple+')
            box_colors.append(colors[2])
        
        if box_data:
            bp = ax2.boxplot(box_data, labels=box_labels, patch_artist=True)
            for patch, color in zip(bp['boxes'], box_colors):
                patch.set_facecolor(color)
        
        ax2.set_ylabel('Voltage (V)', fontsize=11)
        ax2.set_title('Voltage Distribution by Spike Count', fontsize=13, fontweight='bold')
        ax2.grid(True, alpha=0.3, axis='y')
        
        # Add mean markers
        for i, (data, color) in enumerate(zip(box_data, box_colors)):
            ax2.plot([i+1], [data.mean()], marker='D', color=color, 
                    markersize=8, markeredgecolor='black')
        
        # 3. Time comparison boxplot
        ax3 = axes[0, 2]
        time_data = []
        if len(t_single) > 0:
            time_data.append(t_single)
        if len(t_double) > 0:
            time_data.append(t_double)
        if len(t_triple) > 0:
            time_data.append(t_triple)
        
        if time_data:
            bp = ax3.boxplot(time_data, labels=box_labels, patch_artist=True)
            for patch, color in zip(bp['boxes'], box_colors):
                patch.set_facecolor(color)
        
        ax3.set_ylabel('Time Since Last Spike (μs)', fontsize=11)
        ax3.set_title('Time Distribution by Spike Count', fontsize=13, fontweight='bold')
        ax3.grid(True, alpha=0.3, axis='y')
        
        # Add mean markers
        for i, (data, color) in enumerate(zip(time_data, box_colors)):
            ax3.plot([i+1], [data.mean()], marker='D', color=color, 
                    markersize=8, markeredgecolor='black')
        
        # 4. Voltage histograms
        ax4 = axes[1, 0]
        if len(v_single) > 0:
            ax4.hist(v_single, bins=30, alpha=0.6, color=colors[0], 
                    label='Single', edgecolor='black', linewidth=0.5)
        if len(v_double) > 0:
            ax4.hist(v_double, bins=30, alpha=0.6, color=colors[1], 
                    label='Double', edgecolor='black', linewidth=0.5)
        if len(v_triple) > 0:
            ax4.hist(v_triple, bins=30, alpha=0.6, color=colors[2], 
                    label='Triple+', edgecolor='black', linewidth=0.5)
        
        ax4.set_xlabel('Voltage (V)', fontsize=11)
        ax4.set_ylabel('Frequency', fontsize=11)
        ax4.set_title('Voltage Histograms', fontsize=13, fontweight='bold')
        ax4.legend()
        ax4.grid(True, alpha=0.3, axis='y')
        
        # 5. Time histograms
        ax5 = axes[1, 1]
        if len(t_single) > 0:
            ax5.hist(t_single, bins=30, alpha=0.6, color=colors[0], 
                    label='Single', edgecolor='black', linewidth=0.5)
        if len(t_double) > 0:
            ax5.hist(t_double, bins=30, alpha=0.6, color=colors[1], 
                    label='Double', edgecolor='black', linewidth=0.5)
        if len(t_triple) > 0:
            ax5.hist(t_triple, bins=30, alpha=0.6, color=colors[2], 
                    label='Triple+', edgecolor='black', linewidth=0.5)
        
        ax5.set_xlabel('Time Since Last Spike (μs)', fontsize=11)
        ax5.set_ylabel('Frequency', fontsize=11)
        ax5.set_title('Time Histograms', fontsize=13, fontweight='bold')
        ax5.legend()
        ax5.grid(True, alpha=0.3, axis='y')
        
        # 6. Statistical summary table
        ax6 = axes[1, 2]
        ax6.axis('off')
        
        stats_data = [['Metric', 'Single', 'Double', 'Triple+']]
        
        # Count
        stats_data.append(['Count', 
                          f'{len(v_single)}' if len(v_single) > 0 else '0',
                          f'{len(v_double)}' if len(v_double) > 0 else '0',
                          f'{len(v_triple)}' if len(v_triple) > 0 else '0'])
        
        # Voltage stats
        stats_data.append(['V Mean (V)', 
                          f'{v_single.mean():.4f}' if len(v_single) > 0 else 'N/A',
                          f'{v_double.mean():.4f}' if len(v_double) > 0 else 'N/A',
                          f'{v_triple.mean():.4f}' if len(v_triple) > 0 else 'N/A'])
        
        stats_data.append(['V Std (V)', 
                          f'{v_single.std():.4f}' if len(v_single) > 0 else 'N/A',
                          f'{v_double.std():.4f}' if len(v_double) > 0 else 'N/A',
                          f'{v_triple.std():.4f}' if len(v_triple) > 0 else 'N/A'])
        
        # Time stats
        stats_data.append(['T Mean (μs)', 
                          f'{t_single.mean():.2f}' if len(t_single) > 0 else 'N/A',
                          f'{t_double.mean():.2f}' if len(t_double) > 0 else 'N/A',
                          f'{t_triple.mean():.2f}' if len(t_triple) > 0 else 'N/A'])
        
        stats_data.append(['T Std (μs)', 
                          f'{t_single.std():.2f}' if len(t_single) > 0 else 'N/A',
                          f'{t_double.std():.2f}' if len(t_double) > 0 else 'N/A',
                          f'{t_triple.std():.2f}' if len(t_triple) > 0 else 'N/A'])
        
        table = ax6.table(cellText=stats_data, cellLoc='center', loc='center',
                         colWidths=[0.25, 0.25, 0.25, 0.25])
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.8)
        
        # Style header row
        for i in range(4):
            table[(0, i)].set_facecolor('#34495e')
            table[(0, i)].set_text_props(weight='bold', color='white')
        
        # Style data rows with spike-specific colors
        for i in range(1, len(stats_data)):
            table[(i, 0)].set_facecolor('#f8f9fa')  # Metric column
            table[(i, 1)].set_facecolor('#ebf3fd')  # Single spike - light blue
            table[(i, 2)].set_facecolor('#fdf2e9')  # Double spike - light red  
            table[(i, 3)].set_facecolor('#fef9e7')  # Triple+ spike - light orange
        
        ax6.set_title('Statistical Summary', fontsize=13, fontweight='bold', pad=20)
        
        plt.suptitle('Multi-Spike Analysis by Spike Count (1, 2, 3+)', fontsize=16, fontweight='bold')
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        # # plt.show()
        
        # Print detailed statistics
        print("\nDetailed Statistics:")
        print("-" * 60)
        
        if len(v_single) > 0:
            print(f"Single Spike Cycles ({len(v_single)} samples):")
            print(f"  Voltage: {v_single.mean():.4f} ± {v_single.std():.4f} V")
            print(f"  Time: {t_single.mean():.2f} ± {t_single.std():.2f} μs")
        
        if len(v_double) > 0:
            print(f"Double Spike Cycles ({len(v_double)} samples):")
            print(f"  Voltage: {v_double.mean():.4f} ± {v_double.std():.4f} V")
            print(f"  Time: {t_double.mean():.2f} ± {t_double.std():.2f} μs")
        
        if len(v_triple) > 0:
            print(f"Triple+ Spike Cycles ({len(v_triple)} samples):")
            print(f"  Voltage: {v_triple.mean():.4f} ± {v_triple.std():.4f} V")
            print(f"  Time: {t_triple.mean():.2f} ± {t_triple.std():.2f} μs")
    
    def plot_theoretical_curves(self, R_guesses: List[float] = None, save_path: str = None):
        """
        Plot theoretical discharge curves for different R values.
        
        Args:
            R_guesses: List of resistance values to plot (in Ohms)
        """
        if self.data is None:
            print("No data loaded. Call load_and_parse_data() first.")
            return
        
        if R_guesses is None:
            # Default guesses spanning several orders of magnitude
            R_guesses = [1e9, 5e8, 1e9, 5e9, 1e10]
        
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        
        v = self.data['v_currents']
        t = self.data['gt_times']
        
        # Plot 1: Linear scale
        ax1 = axes[0]
        ax1.scatter(v, t, alpha=0.3, s=20, color='gray', label='Actual Data', zorder=1)
        
        # Generate theoretical curves
        v_range = np.linspace(v.min(), min(v.max(), self.v_initial_guess * 0.99), 200)
        
        colors = plt.cm.rainbow(np.linspace(0, 1, len(R_guesses)))
        
        for R, color in zip(R_guesses, colors):
            # t = -RC * ln(V/V0)
            C = 30e-12  # 30 pF from paper
            tau = R * C
            t_theoretical = -tau * np.log(v_range / self.v_initial_guess) * 1e6  # Convert to μs
            
            ax1.plot(v_range, t_theoretical, color=color, linewidth=2, 
                    label=f'R = {R:.1e} Ω', zorder=2)
        
        ax1.set_xlabel('Voltage (V)', fontsize=12)
        ax1.set_ylabel('Time (μs)', fontsize=12)
        ax1.set_title('Theoretical Discharge Curves vs Actual Data', fontsize=14, fontweight='bold')
        ax1.legend(loc='best', fontsize=10)
        ax1.grid(True, alpha=0.3)
        
        # Plot 2: Log scale
        ax2 = axes[1]
        ax2.scatter(v, t, alpha=0.3, s=20, color='gray', label='Actual Data', zorder=1)
        
        for R, color in zip(R_guesses, colors):
            C = 30e-12
            tau = R * C
            t_theoretical = -tau * np.log(v_range / self.v_initial_guess) * 1e6
            
            ax2.plot(v_range, t_theoretical, color=color, linewidth=2, 
                    label=f'R = {R:.1e} Ω', zorder=2)
        
        ax2.set_xlabel('Voltage (V)', fontsize=12)
        ax2.set_ylabel('Time (μs) - Log Scale', fontsize=12)
        ax2.set_yscale('log')
        ax2.set_title('Theoretical Curves (Log Scale)', fontsize=14, fontweight='bold')
        ax2.legend(loc='best', fontsize=10)
        ax2.grid(True, alpha=0.3, which='both')
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        # plt.show()
    
    def plot_outlier_analysis(self, save_path: str = None):
        """
        Analyze and visualize potential outliers.
        """
        if self.data is None:
            print("No data loaded. Call load_and_parse_data() first.")
            return
        
        v = self.data['v_currents']
        t = self.data['gt_times']
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # 1. Box plot for voltage
        ax1 = axes[0, 0]
        bp1 = ax1.boxplot(v, vert=True, patch_artist=True)
        bp1['boxes'][0].set_facecolor('lightblue')
        ax1.set_ylabel('Voltage (V)', fontsize=12)
        ax1.set_title('Voltage Outlier Detection', fontsize=12, fontweight='bold')
        ax1.grid(True, alpha=0.3, axis='y')
        
        # Calculate and display outliers
        q1_v, q3_v = np.percentile(v, [25, 75])
        iqr_v = q3_v - q1_v
        lower_v = q1_v - 1.5 * iqr_v
        upper_v = q3_v + 1.5 * iqr_v
        outliers_v = np.sum((v < lower_v) | (v > upper_v))
        ax1.text(0.5, 0.95, f'Outliers: {outliers_v} ({outliers_v/len(v)*100:.1f}%)', 
                transform=ax1.transAxes, fontsize=10, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        # 2. Box plot for time
        ax2 = axes[0, 1]
        bp2 = ax2.boxplot(t, vert=True, patch_artist=True)
        bp2['boxes'][0].set_facecolor('lightcoral')
        ax2.set_ylabel('Time (μs)', fontsize=12)
        ax2.set_title('Time Outlier Detection', fontsize=12, fontweight='bold')
        ax2.grid(True, alpha=0.3, axis='y')
        
        q1_t, q3_t = np.percentile(t, [25, 75])
        iqr_t = q3_t - q1_t
        lower_t = q1_t - 1.5 * iqr_t
        upper_t = q3_t + 1.5 * iqr_t
        outliers_t = np.sum((t < lower_t) | (t > upper_t))
        ax2.text(0.5, 0.95, f'Outliers: {outliers_t} ({outliers_t/len(t)*100:.1f}%)', 
                transform=ax2.transAxes, fontsize=10, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        # 3. Z-score scatter plot
        ax3 = axes[1, 0]
        z_v = (v - v.mean()) / v.std()
        z_t = (t - t.mean()) / t.std()
        
        outlier_mask = (np.abs(z_v) > 3) | (np.abs(z_t) > 3)
        
        ax3.scatter(z_v[~outlier_mask], z_t[~outlier_mask], alpha=0.5, s=20, 
                   color='blue', label='Normal')
        ax3.scatter(z_v[outlier_mask], z_t[outlier_mask], alpha=0.7, s=40, 
                   color='red', label='Outliers (|z| > 3)')
        
        ax3.axhline(y=3, color='red', linestyle='--', alpha=0.5)
        ax3.axhline(y=-3, color='red', linestyle='--', alpha=0.5)
        ax3.axvline(x=3, color='red', linestyle='--', alpha=0.5)
        ax3.axvline(x=-3, color='red', linestyle='--', alpha=0.5)
        
        ax3.set_xlabel('Voltage Z-Score', fontsize=12)
        ax3.set_ylabel('Time Z-Score', fontsize=12)
        ax3.set_title(f'Z-Score Analysis ({np.sum(outlier_mask)} outliers)', 
                     fontsize=12, fontweight='bold')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        # 4. Residual plot (if we know approximate R)
        ax4 = axes[1, 1]
        
        # Use a reasonable R guess for residual calculation
        R_guess = 50e6  # 1 GΩ
        C = 30e-12
        tau = R_guess * C
        t_predicted = -tau * np.log(v / self.v_initial_guess) * 1e6
        residuals = t - t_predicted
        
        ax4.scatter(t, residuals, alpha=0.5, s=20, color='purple')
        ax4.axhline(y=0, color='red', linestyle='--', linewidth=2)
        
        # Add ±2σ bounds
        sigma = residuals.std()
        ax4.axhline(y=2*sigma, color='orange', linestyle='--', alpha=0.5, label='±2σ')
        ax4.axhline(y=-2*sigma, color='orange', linestyle='--', alpha=0.5)
        
        ax4.set_xlabel('Actual Time (μs)', fontsize=12)
        ax4.set_ylabel('Residual (μs)', fontsize=12)
        ax4.set_title(f'Residuals (assuming R={R_guess:.1e} Ω)', 
                     fontsize=12, fontweight='bold')
        ax4.legend()
        ax4.grid(True, alpha=0.3)
        
        plt.suptitle('Outlier Analysis', fontsize=16, fontweight='bold', y=0.995)
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        # plt.show()


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Generate comprehensive EDA reports from neural spike dataset JSON files.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single file
  %(prog)s --input data.json --output report.pdf
  %(prog)s -i neural_data/data.json
  
  # Multiple files (stitched together)
  %(prog)s -i file1.json file2.json file3.json
  %(prog)s -i neural_data/*.json -o combined_report.pdf
        """
    )
    
    parser.add_argument(
        '-i', '--input',
        type=str,
        nargs='+',
        default=None,
        help='Path(s) to input JSON dataset file(s). Multiple files will be stitched together.'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        default=None,
        help='Path to output PDF report file (default: auto-generated based on input filename)'
    )
    
    parser.add_argument(
        '-v', '--v-initial',
        type=float,
        default=1.9,
        help='Initial voltage guess for analysis (default: 1.9V)'
    )
    
    parser.add_argument(
        '--r-guesses',
        type=float,
        nargs='+',
        default=[3.2e8, 4.5e8, 6e8],
        help='Resistance values (in Ohms) for theoretical curve fitting (default: 3.2e8 4.5e8 6e8)'
    )
    
    parser.add_argument(
        '--no-plots',
        action='store_true',
        help='Skip generating individual plot files (only generate PDF report)'
    )
    
    return parser.parse_args()



def generate_eda_report(explorer, output_path="eda_report.pdf", 
                        dataset_name="Neural Dataset Analysis",
                        r_guesses=None,
                        dataset_path=None):
    """
    Generate a comprehensive PDF report with all EDA plots and statistics.
    
    Args:
        explorer: DatasetExplorer instance with loaded data
        output_path: Path for the output PDF file
        dataset_name: Name of the dataset for the report title
        r_guesses: List of resistance values for theoretical curves
        dataset_path: Path to the dataset file
    """
    if explorer.data is None:
        print("No data loaded in explorer. Cannot generate report.")
        return
    
    if r_guesses is None:
        r_guesses = [3.2e8, 4.5e8, 6e8]
    
    if dataset_path is None:
        dataset_path = "unknown"
    
    # Create temporary image files
    temp_files = []
    eda_path = "temp_eda.png"
    theory_path = "temp_theory.png"
    outlier_path = "temp_outlier.png"
    multi_spike_path = "temp_multispike.png"
    
    try:
        # Generate all plots
        print("Generating EDA plots...")
        explorer.plot_comprehensive_eda(save_path=eda_path)
        temp_files.append(eda_path)
        
        print("Generating theoretical curves...")
        explorer.plot_theoretical_curves(save_path=theory_path, R_guesses=r_guesses)
        temp_files.append(theory_path)
        
        print("Generating outlier analysis...")
        explorer.plot_outlier_analysis(save_path=outlier_path)
        temp_files.append(outlier_path)
        
        print("Multispike comparison plot...")
        explorer.plot_multispike_comparison(save_path=multi_spike_path)
        temp_files.append(multi_spike_path)
    
        
        # Create PDF
        print(f"Creating PDF report: {output_path}")
        doc = SimpleDocTemplate(output_path, pagesize=A4,
                                rightMargin=72, leftMargin=72,
                                topMargin=72, bottomMargin=18)
        
        # Container for the 'Flowable' objects
        story = []
        
        # Get styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            spaceAfter=12,
            spaceBefore=20,
        )
        
        # Title page
        story.append(Paragraph(dataset_name, title_style))
        story.append(Paragraph("Exploratory Data Analysis Report", title_style))
        story.append(Spacer(1, 20))
        story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 
                                styles['Normal']))
        story.append(Spacer(1, 20))
        story.append(Paragraph(f"Dataset: {dataset_path}", styles['Normal']))
        # story.append(PageBreak())
        
        # Executive Summary
        story.append(Paragraph("Executive Summary", heading_style))
        
        summary_text = f"""
        This report presents a comprehensive exploratory data analysis of the neural dataset containing 
        {explorer.data['total_samples']} total samples with {explorer.data['valid_samples']} valid data points 
        ({explorer.data['valid_samples']/explorer.data['total_samples']*100:.1f}% validity rate).
        
        The dataset represents capacitor discharge measurements with voltage readings ranging from 
        {explorer.data['v_currents'].min():.4f}V to {explorer.data['v_currents'].max():.4f}V and 
        time measurements from {explorer.data['gt_times'].min():.1f}μs to {explorer.data['gt_times'].max():.1f}μs.
        
        Key findings include data quality assessment, voltage and time distributions, theoretical model 
        comparisons, and outlier identification to support subsequent modeling efforts.
        """
        
        story.append(Paragraph(summary_text, styles['Normal']))
        story.append(PageBreak())
        
        # Dataset Statistics
        story.append(Paragraph("Dataset Statistics", heading_style))
        
        # Create statistics table as text
        stats_text = f"""
        <b>Sample Counts:</b><br/>
        • Total Samples: {explorer.data['total_samples']}<br/>
        • Valid Samples: {explorer.data['valid_samples']}<br/>
        • Invalid Samples: {explorer.data['total_samples'] - explorer.data['valid_samples']}<br/>
        • Validity Rate: {explorer.data['valid_samples']/explorer.data['total_samples']*100:.2f}%<br/><br/>
        
        <b>Voltage Statistics:</b><br/>
        • Range: {explorer.data['v_currents'].min():.6f}V - {explorer.data['v_currents'].max():.6f}V<br/>
        • Mean: {explorer.data['v_currents'].mean():.6f}V<br/>
        • Median: {np.median(explorer.data['v_currents']):.6f}V<br/>
        • Standard Deviation: {explorer.data['v_currents'].std():.6f}V<br/><br/>
        
        <b>Spike time Statistics:</b><br/>
        • Range: {explorer.data['gt_times'].min():.1f}μs - {explorer.data['gt_times'].max():.1f}μs<br/>
        • Mean: {explorer.data['gt_times'].mean():.1f}μs<br/>
        • Median: {np.median(explorer.data['gt_times']):.1f}μs<br/>
        • Standard Deviation: {explorer.data['gt_times'].std():.1f}μs<br/><br/>
        
        <b>Cycle Statistics:</b><br/>
        • Mean Cycle Length: {explorer.data['cycle_lengths'].mean():.2f}μs<br/>
        • Median Cycle Length: {np.median(explorer.data['cycle_lengths']):.2f}μs<br/><br/>
        • Max Cycle Length: {explorer.data['cycle_lengths'].max():.2f}μs<br/>
        • Min Cycle Length: {explorer.data['cycle_lengths'].min():.2f}μs<br/>

        <b>Data Quality Issues:</b><br/>
        """
        
        # Add invalid data breakdown
        if explorer.data['invalid_reasons']:
            reasons_count = {}
            for _, reason, _, _ in explorer.data['invalid_reasons']:
                reasons_count[reason] = reasons_count.get(reason, 0) + 1
            for reason, count in reasons_count.items():
                stats_text += f"• {reason.replace('_', ' ').title()}: {count} samples<br/>"
        else:
            stats_text += "• No data quality issues detected<br/>"
        
        story.append(Paragraph(stats_text, styles['Normal']))
        story.append(PageBreak())
        
        # Comprehensive EDA
        story.append(Paragraph("Comprehensive Data Exploration", heading_style))
        story.append(Paragraph("""
        The following visualization provides a comprehensive overview of the dataset including:
        voltage-time relationships, distribution patterns, log-scale analysis, voltage ratios, 
        and overall data quality assessment.
        """, styles['Normal']))
        story.append(Spacer(1, 12))
        
        if os.path.exists(eda_path):
            story.append(Image(eda_path, width=7*inch, height=5.8*inch))
        story.append(PageBreak())
        
        # Theoretical Analysis
        story.append(Paragraph("Theoretical Model Comparison", heading_style))
        story.append(Paragraph("""
        Comparison of actual data against theoretical capacitor discharge curves for different 
        resistance values. This analysis helps identify the optimal resistance parameter range 
        for modeling purposes using the equation: t = -RC × ln(V/V₀)
        """, styles['Normal']))
        story.append(Spacer(1, 12))
        
        if os.path.exists(theory_path):
            story.append(Image(theory_path, width=7*inch, height=3.5*inch))
        story.append(PageBreak())
        
        # Outlier Analysis
        story.append(Paragraph("Outlier Detection and Analysis", heading_style))
        story.append(Paragraph("""
        Comprehensive outlier analysis using multiple statistical methods including box plots, 
        z-score analysis, and residual examination. This analysis identifies potential data 
        points that may require special attention during model training.
        """, styles['Normal']))
        story.append(Spacer(1, 12))
        
        if os.path.exists(outlier_path):
            story.append(Image(outlier_path, width=7*inch, height=5*inch))
        story.append(PageBreak())
        
        # Multi-Spike Comparison
        if os.path.exists(multi_spike_path):
            story.append(Paragraph("Multi-Spike Cycle Comparison", heading_style))
            story.append(Paragraph("""
            Dedicated analysis comparing cycles with different spike counts (1, 2, and 3+ spikes). 
            This section highlights differences in voltage and time distributions across spike counts.
            """, styles['Normal']))
            story.append(Spacer(1, 12))
            story.append(Image(multi_spike_path, width=7*inch, height=5*inch))
            story.append(PageBreak())
        
        # Conclusions and Recommendations
        story.append(Paragraph("Conclusions and Recommendations", heading_style))
        
        v = explorer.data['v_currents']
        t = explorer.data['gt_times']
        outlier_percentage = len([x for x in (v - v.mean()) / v.std() if abs(x) > 3]) / len(v) * 100
        
        conclusions_text = f"""
        <b>Key Findings:</b><br/>
        1. Data quality is high with {explorer.data['valid_samples']/explorer.data['total_samples']*100:.1f}% valid samples<br/>
        2. Voltage distribution shows mean={v.mean():.4f}V with relatively low variance<br/>
        3. Time measurements span {t.max()-t.min():.0f}μs range with mean={t.mean():.1f}μs<br/>
        4. Outlier rate is approximately {outlier_percentage:.1f}% based on z-score analysis<br/><br/>
        
        <b>Recommendations for Modeling:</b><br/>
        • Consider resistance values in the range of 10-100 MΩ based on theoretical curve fitting<br/>
        • Apply outlier filtering with z-score threshold of ±3 for robust model training<br/>
        • Use initial voltage estimate around {explorer.v_initial_guess}V for model initialization<br/>
        • Monitor residual patterns for model validation and improvement opportunities<br/>
        • Consider log-transform of time variable if exponential relationships are assumed<br/><br/>
        
        <b>Data Preprocessing Suggestions:</b><br/>
        • Remove samples with voltage ≥ {explorer.v_initial_guess}V or ≤ 0V<br/>
        • Filter cycles with no spike data or negative time calculations<br/>
        • Consider voltage normalization relative to initial voltage for improved model stability<br/>
        """
        
        story.append(Paragraph(conclusions_text, styles['Normal']))
        
        # Build PDF
        doc.build(story)
        print(f"PDF report successfully generated: {output_path}")
        
    except Exception as e:
        print(f"Error generating PDF report: {str(e)}")
        
    finally:
        # Clean up temporary files
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

def main():
    """Main execution function."""
    args = parse_arguments()
    
    # Validate input file exists
    
    if args.input is None:
        print("Error: Input file must be specified with --input")
        return 1
    
    # Ensure args.input is a list
    if isinstance(args.input, str):
        args.input = [args.input]
    
    # Validate all input files exist
    for input_file in args.input:
        if not os.path.exists(input_file):
            print(f"Error: Input file '{input_file}' not found.")
            return 1
    
    # Generate default output filename if not specified
    if args.output is None:
        if len(args.input) == 1:
            input_basename = os.path.basename(args.input[0])
            input_name = os.path.splitext(input_basename)[0]
            args.output = f"neural_dataset_eda_report_{input_name}.pdf"
        else:
            # Multiple files - use timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            args.output = f"neural_dataset_eda_report_combined_{timestamp}.pdf"
    
    print(f"Input file(s): {', '.join(args.input)}")
    print(f"Output file: {args.output}")
    print(f"Initial voltage: {args.v_initial}V")
    print(f"Resistance guesses: {args.r_guesses}")
    print("-" * 60)
    
    # Initialize explorer
    explorer = DatasetExplorer(v_initial_guess=args.v_initial)
    
    # Load and parse data
    print("\nLoading dataset...")
    try:
        explorer.load_and_parse_data(args.input)
    except FileNotFoundError as e:
        print(f"Error: Could not load file: {e}")
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format: {e}")
        return 1
    except Exception as e:
        print(f"Error loading dataset: {e}")
        return 1
    
    # Print comprehensive statistics
    explorer.print_summary_statistics()
    
    # Create a display path for the dataset
    if len(args.input) == 1:
        dataset_display_path = args.input[0]
    else:
        dataset_display_path = f"{len(args.input)} combined files: {', '.join([os.path.basename(f) for f in args.input])}"
    
    if not args.no_plots:
        # Create comprehensive EDA plots
        print("\nGenerating EDA overview plot...")
        explorer.plot_comprehensive_eda(save_path='eda_overview.png', dataset_path=dataset_display_path)
        
        # Plot theoretical curves with different R values
        print("Generating theoretical curves plot...")
        explorer.plot_theoretical_curves(
            R_guesses=args.r_guesses,
            save_path='theoretical_curves.png'
        )
        
        # Analyze outliers
        print("Generating outlier analysis plot...")
        explorer.plot_outlier_analysis(save_path='outlier_analysis.png')
        
        # Multi-spike comparison
        print("Generating multi-spike comparison plot...")
        # Use first input file for multispike comparison (needs to re-load dataset)
        explorer.plot_multispike_comparison(save_path='multispike_comparison.png', dataset_path=args.input[0] if len(args.input) == 1 else args.input)
    
    # Generate PDF report
    print(f"\nGenerating PDF report: {args.output}")
    generate_eda_report(
        explorer, 
        args.output, 
        "Neural Spike Dataset Analysis",
        args.r_guesses,
        dataset_display_path
    )
    
    print("\n" + "=" * 60)
    print("Processing complete!")
    print("=" * 60)
    
    return 0


# Usage Example (kept for backwards compatibility)
if __name__ == "__main__":
    import sys
    sys.exit(main())

