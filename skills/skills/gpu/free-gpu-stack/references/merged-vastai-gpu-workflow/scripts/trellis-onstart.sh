#!/bin/bash
# TRELLIS on-start script for Vast.ai instances
# Runs once on first boot. Pre-bakes the environment.
set -e

echo "=== TRELLIS environment setup ==="
export DEBIAN_FRONTEND=noninteractive

# System deps
apt-get update -qq && apt-get install -y -qq git wget libgl1-mesa-glx libglib2.0-0 > /dev/null 2>&1

# Install conda if missing
if ! command -v conda &> /dev/null; then
    wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh
    bash /tmp/miniconda.sh -b -p /opt/conda
    export PATH="/opt/conda/bin:$PATH"
    conda init bash
fi

# Clone and setup TRELLIS
if [ ! -d /workspace/TRELLIS ]; then
    cd /workspace
    git clone --recurse-submodules https://github.com/microsoft/TRELLIS.git
    cd TRELLIS
    source /opt/conda/etc/profile.d/conda.sh
    . ./setup.sh --new-env --basic --xformers --flash-attn --diffoctreerast --spconv --mipgaussian --kaolin --nvdiffrast
    
    # Pre-download model (~15GB, saves time on each run)
    source activate trellis
    python3 -c "
from trellis.pipelines import TrellisImageTo3DPipeline
print('Downloading TRELLIS-image-large model...')
TrellisImageTo3DPipeline.from_pretrained('microsoft/TRELLIS-image-large')
print('Model cached.')
"
fi

echo "=== TRELLIS environment ready ==="
