#!/bin/bash

set -e 

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Delay Monitoring FYP Setup ===${NC}\n"


NS3_DIR="../ns-3.46"
if [ ! -d "$NS3_DIR" ]; then
    echo -e "${YELLOW}Warning: NS-3 not found at $NS3_DIR${NC}"
    echo "Please install NS-3 first, then run this script again."
    exit 1
fi


echo "→ Creating symlink to NS-3 scratch directory..."
NS3_SCRATCH="$NS3_DIR/scratch/delay-monitoring"
if [ -L "$NS3_SCRATCH" ]; then
    echo "  ✓ Symlink already exists"
else
    ln -s "$(pwd)/experiments" "$NS3_SCRATCH"
    echo "  ✓ Symlink created: $NS3_SCRATCH"
fi

# 3. Setup Python environment
echo "→ Setting up Python environment..."
cd analysis
if [ -d "venv" ]; then
    echo "  ✓ Virtual environment already exists"
else
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "  ✓ Python environment created"
fi
cd ..

# 4. Create results directory
echo "→ Creating results directory..."
mkdir -p results
touch results/.gitkeep
echo "  ✓ Results directory ready"

# 5. Create named pipes (for real-time mode)
echo "→ Creating named pipes..."
mkfifo /tmp/ns3_to_python 2>/dev/null && echo "  ✓ Created /tmp/ns3_to_python" || echo "  ✓ Pipe already exists"
mkfifo /tmp/python_to_ns3 2>/dev/null && echo "  ✓ Created /tmp/python_to_ns3" || echo "  ✓ Pipe already exists"

echo -e "\n${GREEN}=== Setup Complete! ===${NC}\n"
echo "Next steps:"
echo "  1. cd $NS3_DIR"
echo "  2. ./ns3 build"
echo "  3. ./ns3 run delay-monitoring"
echo ""
echo "To activate Python environment:"
echo "  source analysis/venv/bin/activate"