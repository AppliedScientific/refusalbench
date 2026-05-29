# Changelog

All notable changes to RefusalBench are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] — 2026-05-29

### Added
- **Claude Opus 4.8** added to the main sweep + should-refuse positive control (post-v1.1-frozen; marked `*`). 705 adjudicated trials (total: 14,094) + 75 should-refuse trials (total: 1,500).
- PC Tier A (TPR 100 %); benign 57 %, borderline 93 %, dual-use 100 %, Youden's J +0.43 — walks back Opus 4.7's benign over-refusal (77 % → 57 %).
- "Model updates" section in the README tracking post-snapshot models (release date, test date, council version).

### Changed
- **Council judges rotated to v1.3** (`benchmark/council/v1.1.json`). As of 2026-05-29, `nvidia/llama-3.1-nemotron-70b-instruct` returned HTTP 404 on OpenRouter with no Bedrock deployment, and `cohere.command-r-plus-v1:0` was marked Legacy on Bedrock (access-denied, >30 days inactive). Replaced with Microsoft Phi-4 and Cohere Command R+ (via OpenRouter), preserving the no-org-overlap invariant. Opus 4.8 is adjudicated under this rotated panel; the v1.1-frozen 13,389 rows are unchanged.

---

## [1.1.0] — 2026-05-21

### Added
- **NVIDIA Nemotron Super 3 120B** added to the main sweep panel — panel is now 19 models
- 705 additional adjudicated trials (total: 13,389)
- Should-refuse positive-control results for Nemotron (75 trials, Tier A calibration, 89.3% TPR)
- HuggingFace Space scaffold (`hf_space/`) — Gradio leaderboard ready to deploy on preprint release
- Quarterly snapshot automation workflow (`.github/workflows/quarterly_snapshot.yml`)
- CITATION.cff for machine-readable citation
- CONTRIBUTING.md, CHANGELOG.md, CODE_OF_CONDUCT.md, SECURITY.md
- GitHub issue and pull request templates

### Changed
- `adjudicated.csv` promoted to **v1.1-frozen** status (all analyses now reference this file)
- README updated to reflect 19-model panel and v1.1-frozen snapshot
- `benchmark/config/sweep_models.json` updated with Nemotron routing metadata
- `src/refusalbench/analysis/figures.py` updated: Times New Roman font, full 19-model color palette, figure-prefix stripping, raw-rate labels (fixes Wilson-center 99%→100% display artefact)
- pyproject.toml classifiers and URLs updated for public release

### Fixed
- Figure 3 dual-use label displayed "99%" instead of "100%" due to Wilson center shrinkage at boundary; fixed by tracking `raw_rate` separately from Wilson center

---

## [1.0.0] — 2026-05-01

### Added
- Initial public release
- 18-model main sweep panel; 12,684 adjudicated trials
- 141 v1.0 frozen prompt JSONs across 8 protein-design subdomains and 3 risk tiers
- Three-judge AI council configuration (NVIDIA, Cohere, AI21) — `benchmark/council/v1.1.json`
- Five-class compliance ladder × 16-category reason taxonomy — `benchmark/rubric/v1.0.json`
- Full statistical analysis suite (H1–H5): mixed-effects regression, jurisdiction clustering, subdomain sensitivity, should-refuse calibration, capability correlation
- Should-refuse positive-control module (`scripts/should_refuse_cli.py`)
- CI pipeline: Ruff, Mypy, Pytest on Python 3.11 and 3.12
- 324 unit tests, all mock-driven — no API keys required

---

[1.1.0]: https://github.com/AppliedScientific/refusalbench/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/AppliedScientific/refusalbench/releases/tag/v1.0.0
