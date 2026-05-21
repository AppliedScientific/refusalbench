# Changelog

All notable changes to RefusalBench are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
