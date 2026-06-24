"""
Generate figures for Loop Engineering paper.
"""

import json
import os
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (10, 6)
plt.rcParams['font.size'] = 11

RESULTS_DIR = "/home/novix/workspace/project/experiments/results"
FIGURES_DIR = "/home/novix/workspace/project/experiments/figures"

os.makedirs(FIGURES_DIR, exist_ok=True)


def load_results():
    """Load all experiment results."""
    with open(os.path.join(RESULTS_DIR, "main_results.json")) as f:
        main_results = json.load(f)
    with open(os.path.join(RESULTS_DIR, "ablation_results.json")) as f:
        ablation_results = json.load(f)
    with open(os.path.join(RESULTS_DIR, "redteam_results.json")) as f:
        redteam_results = json.load(f)
    return main_results, ablation_results, redteam_results


def generate_benchmark_results_figure(main_results):
    """Generate main benchmark results bar chart."""
    # Aggregate by task and method
    task_methods = {}
    for r in main_results:
        key = (r['task_name'], r['method'])
        if key not in task_methods:
            task_methods[key] = []
        task_methods[key].append(r['score'])

    # Calculate means
    tasks = sorted(set(r['task_name'] for r in main_results))
    methods = ['one_shot', 'chain_of_thought', 'loop_engine']
    method_labels = ['One-Shot', 'Chain-of-Thought', 'Loop Engine']

    x = np.arange(len(tasks))
    width = 0.25

    fig, ax = plt.subplots(figsize=(12, 6))

    for i, (method, label) in enumerate(zip(methods, method_labels)):
        scores = []
        errors = []
        for task in tasks:
            key = (task, method)
            if key in task_methods:
                values = task_methods[key]
                scores.append(np.mean(values))
                errors.append(np.std(values) / np.sqrt(len(values)))  # SEM
            else:
                scores.append(0)
                errors.append(0)

        ax.bar(x + i * width, scores, width, yerr=errors, label=label, capsize=3)

    ax.set_xlabel('Task')
    ax.set_ylabel('Score')
    ax.set_title('Benchmark Results: Loop Engine vs Baselines')
    ax.set_xticks(x + width)
    ax.set_xticklabels([t.replace(' ', '\n') for t in tasks], fontsize=9)
    ax.legend()
    ax.set_ylim(0, 1.1)

    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'loop-engineering-fig03-benchmark-results.png'), dpi=300)
    plt.close()
    print("Generated: loop-engineering-fig03-benchmark-results.png")


def generate_ablation_figure(ablation_results):
    """Generate ablation study figure."""
    # Aggregate by config
    config_scores = {}
    for r in ablation_results:
        config = r['config']
        if config not in config_scores:
            config_scores[config] = []
        config_scores[config].append(r['score'])

    configs = list(config_scores.keys())
    means = [np.mean(config_scores[c]) for c in configs]
    sems = [np.std(config_scores[c]) / np.sqrt(len(config_scores[c])) for c in configs]

    fig, ax = plt.subplots(figsize=(10, 6))

    colors = ['green' if 'full' in c else 'orange' if c == 'minimal' else 'blue' for c in configs]
    bars = ax.barh(configs, means, xerr=sems, capsize=3, color=colors, alpha=0.7)

    ax.set_xlabel('Score')
    ax.set_title('Ablation Study: Component Importance')
    ax.set_xlim(0, 1.1)

    # Add value labels
    for bar, mean in zip(bars, means):
        ax.text(mean + 0.05, bar.get_y() + bar.get_height()/2, f'{mean:.2f}',
                va='center', fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'loop-engineering-fig04-ablation-study.png'), dpi=300)
    plt.close()
    print("Generated: loop-engineering-fig04-ablation-study.png")


def generate_security_figure(redteam_results):
    """Generate security analysis figure."""
    # Count successes/failures
    total_tests = len(redteam_results)
    succeeded = sum(1 for r in redteam_results if r['injection_succeeded'])
    blocked = total_tests - succeeded

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Pie chart
    ax1.pie([blocked, succeeded], labels=['Blocked', 'Succeeded'], autopct='%1.0f%%',
            colors=['green', 'red'], startangle=90)
    ax1.set_title('Prompt Injection Defense')

    # Bar chart of individual tests
    test_labels = [f"Test {i+1}" for i in range(len(redteam_results))]
    colors = ['red' if r['injection_succeeded'] else 'green' for r in redteam_results]
    ax2.barh(test_labels, [1] * len(redteam_results), color=colors, alpha=0.7)
    ax2.set_xlabel('Blocked' if blocked == total_tests else 'Vulnerability')
    ax2.set_title('Individual Test Results')
    ax2.set_xlim(0, 1.2)

    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'loop-engineering-fig05-security-analysis.png'), dpi=300)
    plt.close()
    print("Generated: loop-engineering-fig05-security-analysis.png")


def generate_architecture_figure():
    """Generate architecture diagram."""
    fig, ax = plt.subplots(figsize=(14, 10))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis('off')

    # Title
    ax.text(5, 9.5, 'Loop Engineering Framework Architecture', ha='center', fontsize=16, fontweight='bold')

    # Core Loop Box
    loop_box = plt.Rectangle((1, 3), 8, 5, fill=True, facecolor='lightblue', edgecolor='black', linewidth=2)
    ax.add_patch(loop_box)
    ax.text(5, 7.5, 'Loop Engine', ha='center', fontsize=14, fontweight='bold')

    # Components
    components = [
        ('Planner', 2, 6.5),
        ('Actor', 5, 6.5),
        ('Observer', 8, 6.5),
        ('Evaluator', 2, 5),
        ('Recovery', 5, 5),
        ('Terminator', 8, 5),
    ]

    for name, x, y in components:
        box = plt.Rectangle((x-0.7, y-0.3), 1.4, 0.6, fill=True, facecolor='white', edgecolor='black')
        ax.add_patch(box)
        ax.text(x, y, name, ha='center', va='center', fontsize=10)

    # Memory
    memory_box = plt.Rectangle((2, 3.5), 6, 0.8, fill=True, facecolor='lightyellow', edgecolor='black')
    ax.add_patch(memory_box)
    ax.text(5, 3.9, 'Memory (Working | Episodic | Consolidated)', ha='center', fontsize=10)

    # Safety & Budget (side boxes)
    safety_box = plt.Rectangle((0.2, 4), 0.7, 3, fill=True, facecolor='lightcoral', edgecolor='black')
    ax.add_patch(safety_box)
    ax.text(0.55, 5.5, 'Safety\nMonitor', ha='center', va='center', fontsize=9, rotation=90)

    budget_box = plt.Rectangle((9.1, 4), 0.7, 3, fill=True, facecolor='lightgreen', edgecolor='black')
    ax.add_patch(budget_box)
    ax.text(9.45, 5.5, 'Budget\nManager', ha='center', va='center', fontsize=9, rotation=90)

    # Arrows showing flow
    ax.annotate('', xy=(5, 6.2), xytext=(5, 5.3),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
    ax.annotate('', xy=(2, 5.8), xytext=(4.3, 5.3),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
    ax.annotate('', xy=(8, 5.8), xytext=(5.7, 5.3),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.5))

    # Input/Output
    ax.text(5, 2, 'Input Goal', ha='center', fontsize=10, style='italic')
    ax.text(5, 1, 'Output Result', ha='center', fontsize=10, style='italic')
    ax.annotate('', xy=(5, 2.7), xytext=(5, 2.3),
                arrowprops=dict(arrowstyle='->', color='black', lw=2))
    ax.annotate('', xy=(5, 1.3), xytext=(5, 0.8),
                arrowprops=dict(arrowstyle='->', color='black', lw=2))

    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'loop-engineering-fig01-architecture.png'), dpi=300)
    plt.close()
    print("Generated: loop-engineering-fig01-architecture.png")


def generate_execution_flow_figure():
    """Generate execution flow diagram."""
    fig, ax = plt.subplots(figsize=(10, 12))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis('off')

    ax.text(5, 11.5, 'Loop Execution Flow', ha='center', fontsize=16, fontweight='bold')

    steps = [
        ('1. PLAN: Create/Revise Plan', 10, 'lightblue'),
        ('2. ACT: Execute Step', 8.5, 'lightgreen'),
        ('3. OBSERVE: Capture Results', 7, 'lightyellow'),
        ('4. EVALUATE: Assess Progress', 5.5, 'lightcoral'),
        ('5. RECOVER: Handle Failures', 4, 'plum'),
        ('6. TERMINATE: Check Completion', 2.5, 'lightgray'),
    ]

    for text, y, color in steps:
        box = plt.Rectangle((1, y-0.4), 8, 0.8, fill=True, facecolor=color, edgecolor='black', linewidth=1.5)
        ax.add_patch(box)
        ax.text(5, y, text, ha='center', va='center', fontsize=11, fontweight='bold')

    # Arrows between steps
    for i in range(len(steps)-1):
        y1 = steps[i][1] - 0.4
        y2 = steps[i+1][1] + 0.4
        ax.annotate('', xy=(5, y2), xytext=(5, y1),
                    arrowprops=dict(arrowstyle='->', color='black', lw=2))

    # Loop back arrow
    ax.annotate('Loop', xy=(8.5, 6), xytext=(8.5, 3),
                arrowprops=dict(arrowstyle='->', color='blue', lw=1.5, connectionstyle="arc3,rad=.3"),
                fontsize=9, color='blue')

    # Exit arrow
    ax.annotate('', xy=(5, 0.8), xytext=(5, 2.1),
                arrowprops=dict(arrowstyle='->', color='green', lw=3))
    ax.text(5, 0.3, 'Output', ha='center', fontsize=11, fontweight='bold', color='green')

    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'loop-engineering-fig02-execution-flow.png'), dpi=300)
    plt.close()
    print("Generated: loop-engineering-fig02-execution-flow.png")


def statistical_analysis(main_results):
    """Perform statistical tests."""
    # Group by method
    method_scores = {'one_shot': [], 'chain_of_thought': [], 'loop_engine': []}
    for r in main_results:
        method_scores[r['method']].append(r['score'])

    results = {}

    # T-tests
    for method in ['one_shot', 'chain_of_thought']:
        t_stat, p_value = stats.ttest_ind(method_scores['loop_engine'], method_scores[method])
        results[f'loop_engine_vs_{method}'] = {
            't_statistic': float(t_stat),
            'p_value': float(p_value),
            'significant': p_value < 0.05
        }

    # Descriptive statistics
    for method, scores in method_scores.items():
        results[f'{method}_stats'] = {
            'mean': float(np.mean(scores)),
            'std': float(np.std(scores)),
            'sem': float(np.std(scores) / np.sqrt(len(scores))),
            'n': len(scores)
        }

    return results


def main():
    print("Loading results...")
    main_results, ablation_results, redteam_results = load_results()

    print("\nGenerating figures...")
    generate_architecture_figure()
    generate_execution_flow_figure()
    generate_benchmark_results_figure(main_results)
    generate_ablation_figure(ablation_results)
    generate_security_figure(redteam_results)

    print("\nPerforming statistical analysis...")
    stats_results = statistical_analysis(main_results)

    with open(os.path.join(RESULTS_DIR, 'statistical_analysis.json'), 'w') as f:
        # Convert numpy types to Python native types for JSON serialization
        def convert(obj):
            if isinstance(obj, np.bool_):
                return bool(obj)
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            return obj
        json.dump(convert(stats_results), f, indent=2)

    print("\nAll figures generated!")
    print(f"Figures saved to: {FIGURES_DIR}")

    # Print summary
    print("\n=== Statistical Summary ===")
    for key, value in stats_results.items():
        if '_vs_' in key:
            print(f"{key}: p={value['p_value']:.4f} {'***' if value['significant'] else 'ns'}")


if __name__ == "__main__":
    main()
