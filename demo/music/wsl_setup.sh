#!/bin/bash
# MusicGen (CPU) environment inside WSL Ubuntu (its disk lives on D:). No sudo: uv provides Python + venv.
set -e
mkdir -p ~/musicgen && cd ~/musicgen
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || (curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1)
uv --version
rm -rf .venv
uv venv -q --python 3.12 .venv
. .venv/bin/activate
uv pip install -q torch --index-url https://download.pytorch.org/whl/cpu
uv pip install -q transformers scipy numpy
python -c "import torch, transformers; print('torch', torch.__version__, 'transformers', transformers.__version__, 'threads', torch.get_num_threads())"
