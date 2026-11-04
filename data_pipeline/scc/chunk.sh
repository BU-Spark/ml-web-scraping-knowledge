#!/bin/bash -l
# Submit from the repository root:
# qsub -P PROJECT data_pipeline/scc/chunk.sh /projectnb/PROJECT/scrape/clean /projectnb/PROJECT/chunking/public_chunks.json
# If your venv needs a Python module, add -v PYTHON_MODULE=python3/VERSION to qsub.

#$ -N semantic_chunk
#$ -cwd
#$ -l h_rt=06:00:00
#$ -j y

set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "Usage: qsub -P PROJECT data_pipeline/scc/chunk.sh CLEAN_INPUT OUTPUT_JSON" >&2
  exit 2
fi

# Select the same Python module used to create .venv. No SCC version is assumed.
if [ -n "${PYTHON_MODULE:-}" ]; then
  module load "$PYTHON_MODULE"
fi

REPO="${REPO:-${SGE_O_WORKDIR:-$PWD}}"
cd "$REPO"
if [ ! -x .venv/bin/python ]; then
  echo "Missing .venv/bin/python. Create the SCC environment and install requirements.txt first." >&2
  exit 1
fi

CHUNK_INPUT="$1"
CHUNK_OUTPUT="$2"
export HF_HOME="${HF_HOME:-$(dirname "$CHUNK_OUTPUT")/model-cache}"
# Keep library parallelism within the scheduler allocation (one CPU by default).
export OMP_NUM_THREADS="${NSLOTS:-1}"
export MKL_NUM_THREADS="${NSLOTS:-1}"
export OPENBLAS_NUM_THREADS="${NSLOTS:-1}"
export TOKENIZERS_PARALLELISM=false

printf 'Repository: %s\nInput: %s\nOutput: %s\n' "$REPO" "$CHUNK_INPUT" "$CHUNK_OUTPUT"
git rev-parse --short HEAD
.venv/bin/python -u -m data_pipeline.chunker \
  --input "$CHUNK_INPUT" \
  --output "$CHUNK_OUTPUT" \
  --model "${CHUNK_EMBED_MODEL:-all-MiniLM-L6-v2}" \
  --threshold 90 --min-chunk-chars 200 --max-chunk-chars 2000 \
  --device cpu --batch-size 32

