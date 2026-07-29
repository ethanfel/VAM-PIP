#!/usr/bin/env bash
set -euo pipefail

SAM3D_COMMIT="b5c765a0d89d789985e186d396315e7590887b94"

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /absolute/path/to/new/vampip-sam3d-runtime" >&2
  exit 2
fi

SAM3D_RUNTIME_INPUT="$1"
case "$SAM3D_RUNTIME_INPUT" in
  /*) ;;
  *)
    echo "The runtime root must be an absolute path." >&2
    exit 2
    ;;
esac

command -v realpath >/dev/null 2>&1 || {
  echo "realpath was not found on PATH." >&2
  exit 2
}

SAM3D_RUNTIME_ROOT="$(realpath -m -- "$SAM3D_RUNTIME_INPUT")"
if [[ "$SAM3D_RUNTIME_ROOT" == "/" ]]; then
  echo "The runtime root cannot be the filesystem root." >&2
  exit 2
fi
if [[ "${SAM3D_RUNTIME_INPUT,,}" == *comfyui* ||
      "${SAM3D_RUNTIME_ROOT,,}" == *comfyui* ]]; then
  echo "Refusing to create the SAM3D runtime inside a ComfyUI tree." >&2
  exit 2
fi

SAM3D_ENV_PREFIX="$(realpath -m -- "$SAM3D_RUNTIME_ROOT/conda")"
SAM3D_REPO_DIR="$(realpath -m -- "$SAM3D_RUNTIME_ROOT/sam-3d-body")"
SAM3D_MODEL_DIR="$(realpath -m -- "$SAM3D_RUNTIME_ROOT/models/vith")"
SAM3D_HF_HOME="$(realpath -m -- "$SAM3D_RUNTIME_ROOT/cache/huggingface")"

for target in \
  "$SAM3D_ENV_PREFIX" \
  "$SAM3D_REPO_DIR" \
  "$SAM3D_MODEL_DIR" \
  "$SAM3D_HF_HOME"; do
  if [[ "${target,,}" == *comfyui* ]]; then
    echo "Refusing a path that resolves inside a ComfyUI tree: $target" >&2
    exit 2
  fi
  case "$target" in
    "$SAM3D_RUNTIME_ROOT"/*) ;;
    *)
      echo "Refusing a path that escapes the standalone runtime: $target" >&2
      exit 2
      ;;
  esac
done

for target in "$SAM3D_ENV_PREFIX" "$SAM3D_REPO_DIR"; do
  if [[ -e "$target" ]]; then
    echo "Refusing to overwrite existing path: $target" >&2
    exit 2
  fi
done

command -v conda >/dev/null 2>&1 || {
  echo "conda was not found on PATH." >&2
  exit 2
}
command -v git >/dev/null 2>&1 || {
  echo "git was not found on PATH." >&2
  exit 2
}

mkdir -p "$SAM3D_RUNTIME_ROOT" "$SAM3D_MODEL_DIR" "$SAM3D_HF_HOME"
conda create --prefix "$SAM3D_ENV_PREFIX" python=3.11 pip -y
git clone https://github.com/facebookresearch/sam-3d-body.git "$SAM3D_REPO_DIR"
git -C "$SAM3D_REPO_DIR" checkout --detach "$SAM3D_COMMIT"

cat <<EOF

Created an isolated Python 3.11 environment and pinned native Meta checkout.
No model, PyTorch build, or Python dependencies were downloaded.

Next:
  1. Install a current RTX 5090/Blackwell-compatible PyTorch build into:
       $SAM3D_ENV_PREFIX
  2. Follow docs/SAM3D_SETUP.md for dependencies and gated ViT-H download.
     Keep its setup commands isolated with:
       HF_HOME=$SAM3D_HF_HOME
  3. Configure VAM-PIP with:
       VAMPIP_SAM3D_PYTHON=$SAM3D_ENV_PREFIX/bin/python
       VAMPIP_SAM3D_REPO=$SAM3D_REPO_DIR
       VAMPIP_SAM3D_CHECKPOINT=$SAM3D_MODEL_DIR/model.ckpt
       VAMPIP_SAM3D_MHR=$SAM3D_MODEL_DIR/assets/mhr_model.pt
EOF
