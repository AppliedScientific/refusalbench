#!/usr/bin/env python3
"""
Push the RefusalBench HuggingFace Space.

Usage (token never touches shell history):
    python3 scripts/push_hf_space.py          # prompts securely
    HF_TOKEN=hf_... python3 scripts/push_hf_space.py  # from env var

The token is read once, used, then discarded — never written to disk.
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

REPO_ID   = "AppliedScientific/refusalbench"
SPACE_DIR = Path(__file__).parent.parent / "hf_space"
COMMIT_MSG = "Deploy RefusalBench leaderboard (v1.1-frozen, arXiv:2605.21545)"


def main() -> None:
    # ── 1. Get token ──────────────────────────────────────────────────────────
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        print("Paste your HuggingFace token (Write scope required).")
        print("Get one at: https://huggingface.co/settings/tokens\n")
        token = getpass.getpass("HF token (input hidden): ").strip()
    if not token:
        sys.exit("✗  No token provided — aborted.")

    # ── 2. Import ──────────────────────────────────────────────────────────────
    try:
        from huggingface_hub import HfApi
    except ImportError:
        sys.exit(
            "✗  huggingface_hub not installed.\n"
            "   Run: pip install huggingface_hub"
        )

    api = HfApi(token=token)

    # ── 3. Verify token ────────────────────────────────────────────────────────
    try:
        user = api.whoami()
        print(f"✓  Authenticated as: {user['name']}")
    except Exception as exc:
        sys.exit(f"✗  Token invalid: {exc}")

    # ── 4. Verify source directory ─────────────────────────────────────────────
    if not SPACE_DIR.exists():
        sys.exit(f"✗  hf_space/ directory not found at: {SPACE_DIR}")

    files = list(SPACE_DIR.rglob("*"))
    file_list = "\n".join(
        f"   {f.relative_to(SPACE_DIR)}"
        for f in sorted(files)
        if f.is_file()
    )
    print(f"\nFiles to upload from hf_space/:\n{file_list}\n")

    # ── 5. Ensure Space exists ─────────────────────────────────────────────────
    try:
        api.repo_info(repo_id=REPO_ID, repo_type="space")
        print(f"✓  Space exists — updating: https://huggingface.co/spaces/{REPO_ID}")
    except Exception:
        print(f"   Space not found — creating {REPO_ID} ...")
        api.create_repo(
            repo_id=REPO_ID,
            repo_type="space",
            space_sdk="gradio",
            exist_ok=True,
        )
        print("✓  Space created.")

    # ── 6. Upload ──────────────────────────────────────────────────────────────
    print("Uploading … (the adjudicated.csv is ~1.8 MB, may take a moment)\n")
    api.upload_folder(
        folder_path=str(SPACE_DIR),
        repo_id=REPO_ID,
        repo_type="space",
        commit_message=COMMIT_MSG,
    )

    # ── 7. Done ────────────────────────────────────────────────────────────────
    print(f"\n✓  Upload complete.")
    print(f"   Space URL : https://huggingface.co/spaces/{REPO_ID}")
    print(f"   Build log : https://huggingface.co/spaces/{REPO_ID}?logs=build")
    print(f"\n   Allow ~1–2 minutes for the Space to build and go live.\n")

    # Discard token from local namespace
    token = None  # noqa: F841


if __name__ == "__main__":
    main()
