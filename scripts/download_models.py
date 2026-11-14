"""Download the Kimodo SOMA motion model + LLM2Vec text encoder (GGUF) from Hugging Face and verify SHA-256.

Mirrors kimodo.cpp's scripts/download_gguf_weights.py (Apache-2.0) so end users don't need the kimodo.cpp source.
Usage: python scripts/download_models.py [--quant q4_k_m|q8_0] [--output models]
"""
import argparse, hashlib, json, sys
from pathlib import Path
from huggingface_hub import hf_hub_download

ORG = "LocalAI-io"
MOTION = (f"{ORG}/Kimodo-SOMA-RP-v1.1-GGML", "models/kimodo-soma-rp-v1.1-f32.gguf")
TEXT_REPO = f"{ORG}/Llama-3-Kimodo-GGML"


def manifest(repo: str, out: Path) -> dict:
    p = hf_hub_download(repo_id=repo, filename="MANIFEST.json", local_dir=out / ".manifests" / repo.replace("/", "__"))
    m = json.loads(Path(p).read_text(encoding="utf-8"))
    if m.get("format") != "kimodo-gguf-manifest-v1":
        sys.exit(f"unexpected manifest format in {repo}")
    return m


def fetch(repo: str, rel: str, m: dict, out: Path) -> None:
    entry = next((e for e in m.get("files", []) if e.get("path") == rel), None)
    if entry is None:
        sys.exit(f"{rel} not listed in {repo} manifest")
    target = out / rel
    if target.exists() and target.stat().st_size == entry["bytes"]:
        print(f"  {rel}: present, verifying...")
    else:
        print(f"  downloading {rel} ({entry['bytes'] / 2**30:.2f} GB) from {repo} ...")
        hf_hub_download(repo_id=repo, filename=rel, local_dir=out)
    h = hashlib.sha256()
    with target.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    if target.stat().st_size != entry["bytes"] or h.hexdigest() != entry["sha256"]:
        sys.exit(f"checksum mismatch for {target}; delete it and re-run")
    print(f"  {rel}: OK")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quant", default="q4_k_m", choices=["q4_k_m", "q5_k", "q6_k", "q8_0"])
    ap.add_argument("--output", default=str(Path(__file__).resolve().parents[1] / "models"))
    a = ap.parse_args()
    out = Path(a.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    print("Motion model (NVIDIA Open Model License):")
    fetch(MOTION[0], MOTION[1], manifest(MOTION[0], out), out)
    print(f"Text encoder {a.quant} (Meta Llama 3 Community License):")
    m = manifest(TEXT_REPO, out)
    v = m["variants"][a.quant]
    for rel in (v["tokenizer"], v["weights"]):
        fetch(TEXT_REPO, rel, m, out)
    print("All models downloaded and verified.")


if __name__ == "__main__":
    main()
