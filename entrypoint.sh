#!/bin/bash
# Entrypoint script for Loop Engineering Framework
# This script reproduces all experimental results

set -e

echo "=========================================="
echo "Loop Engineering Framework - Reproduction"
echo "=========================================="

# Change to project directory
cd /home/novix/workspace/project

echo ""
echo "Step 1: Installing dependencies..."
pip install -q numpy matplotlib seaborn scipy 2>/dev/null || true

echo ""
echo "Step 2: Running experiments..."
python experiments/runner.py

echo ""
echo "Step 3: Generating figures..."
python experiments/generate_figures.py

echo ""
echo "=========================================="
echo "Reproduction Complete!"
echo "=========================================="
echo ""
echo "Results saved to:"
echo "  - experiments/results/main_results.json"
echo "  - experiments/results/ablation_results.json"
echo "  - experiments/results/redteam_results.json"
echo ""
echo "Figures saved to:"
echo "  - experiments/figures/loop-engineering-fig01-architecture.png"
echo "  - experiments/figures/loop-engineering-fig02-execution-flow.png"
echo "  - experiments/figures/loop-engineering-fig03-benchmark-results.png"
echo "  - experiments/figures/loop-engineering-fig04-ablation-study.png"
echo "  - experiments/figures/loop-engineering-fig05-security-analysis.png"
echo ""
echo "Handoff document:"
echo "  - HANDOFF_TO_WRITER.md"
echo ""
