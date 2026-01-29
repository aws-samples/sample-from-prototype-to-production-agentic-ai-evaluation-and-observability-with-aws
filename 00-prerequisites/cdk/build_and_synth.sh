#!/bin/bash
#
# E-Commerce Agent Workshop - CDK Build and Synthesize Script
#
# This script:
# 1. Sets up the Python virtual environment
# 2. Installs dependencies
# 3. Synthesizes CloudFormation templates
#
# Usage:
#   ./build_and_synth.sh              # Synthesize to cdk.out/
#   ./build_and_synth.sh --output-dir ./cfn  # Synthesize to custom directory
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Parse arguments
OUTPUT_DIR=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: ./build_and_synth.sh [--output-dir <directory>]"
            exit 1
            ;;
    esac
done

echo "========================================"
echo "E-Commerce Workshop CDK Build & Synth"
echo "========================================"

# Step 1: Create/activate virtual environment
echo ""
echo "Step 1: Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

# Step 2: Install dependencies
echo ""
echo "Step 2: Installing dependencies..."
pip install -r requirements.txt --quiet

# Step 3: Synthesize CloudFormation
echo ""
echo "Step 3: Synthesizing CloudFormation templates..."
if [ -n "$OUTPUT_DIR" ]; then
    mkdir -p "$OUTPUT_DIR"
    cdk synth --output "$OUTPUT_DIR"
    echo ""
    echo "CloudFormation templates generated in: $OUTPUT_DIR"
    echo ""
    echo "Files:"
    ls -la "$OUTPUT_DIR"/*.template.json 2>/dev/null || ls -la "$OUTPUT_DIR"/*.yaml 2>/dev/null || echo "  (templates in $OUTPUT_DIR)"
else
    cdk synth
    echo ""
    echo "CloudFormation templates generated in: cdk.out/"
    echo ""
    echo "Files:"
    ls -la cdk.out/*.template.json 2>/dev/null || echo "  (see cdk.out/ directory)"
fi

echo ""
echo "========================================"
echo "Build and synthesis complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  - Review: cdk diff"
echo "  - Deploy: cdk deploy"
echo "  - Destroy: cdk destroy"
echo ""
