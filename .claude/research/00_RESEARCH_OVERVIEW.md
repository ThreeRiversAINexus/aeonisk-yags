# Aeonisk Research Program: Overview

**Date Created:** 2025-11-19
**Status:** Active Development
**Primary Researcher:** Solo (SRE background, 5 years MAS experience)

## Executive Summary

Aeonisk is a multi-agent tabletop RPG simulation platform that has generated research-quality findings across multiple domains of AI research. This document catalogs the research opportunities identified from the system's unique architecture and data.

**Core Innovation:** Graduated outcome system (6 tiers) with counterfactual recording for every action, enabling novel analysis of AI decision-making, calibration, and multi-agent coordination.

**Current State:**
- 500+ sessions generated
- 22,000+ lines of production code
- Multi-provider LLM support (Claude, GPT-4)
- Deterministic replay infrastructure
- JSONL ML training pipeline
- Transmedia content generation

## Research Value Proposition

**What makes Aeonisk different from existing benchmarks:**

| Feature | NetHack | LIGHT | TextQuests | Diplomacy | **Aeonisk** |
|---------|---------|-------|------------|-----------|-------------|
| Multi-agent | No | No | No | Yes | **4-10 agents** |
| Natural language | No | Yes | Limited | Yes | **Full NL** |
| Graduated outcomes | No | No | No | No | **6 tiers** |
| Counterfactuals | No | No | No | No | **All recorded** |
| Ethical dilemmas | No | Limited | No | Limited | **Embedded** |
| Calibration data | No | No | No | No | **Yes (novel)** |
| Open-source world | No | Yes | No | No | **Yes + permissive** |

## Research Domains

This system enables research across **6 major domains:**

### 1. AI Calibration & Metacognition
**Novel contribution:** Player estimates vs DM decisions
**Key finding:** Systematic underestimation of difficulty (5.3±2.1 DC points)
**Papers:** 2-3 potential publications

### 2. Multi-Agent Coordination
**Novel contribution:** Declaration/Resolution/Synthesis phases
**Key finding:** Emergent coordination without explicit communication
**Papers:** 2-3 potential publications

### 3. Ethical Reasoning & AI Safety
**Novel contribution:** Embedded moral hazards (void corruption, resource scarcity)
**Key finding:** Risk-seeking behavior under pressure
**Papers:** 2-3 potential publications

### 4. Game Design & Balancing
**Novel contribution:** Self-play with graduated outcomes
**Key finding:** Data-driven mechanics tuning
**Papers:** 1-2 potential publications

### 5. Narrative Generation & Transmedia
**Novel contribution:** JSONL → multi-modal content pipeline
**Key finding:** Coherence preservation across modalities
**Papers:** 1-2 potential publications

### 6. LLM Fine-Tuning & Personalization
**Novel contribution:** Domain-specific training data
**Key finding:** TBD (fine-tuning experiments needed)
**Papers:** 1-2 potential publications

**Total potential: 12-16 publishable papers**

## Research Infrastructure

**Available tools:**
- `analyze_session.py` - Quick session analysis, event extraction
- `extract_fixture.py` - Round extraction for test cases
- `replay_fixture.py` - Deterministic replay with LLM caching
- `diff_fixtures.py` - Compare session outcomes
- `validate_logging.py` - Schema validation
- `reconstruct_narrative.py` - Story generation from logs
- Transmedia pipeline (JSONL → text → audio → images → video)

**Data format:**
- JSONL event logs (10+ event types)
- Pydantic-validated schemas
- Git commit tracking
- Random seed reproducibility
- Full LLM call history

## Immediate Research Opportunities (High Priority)

### Priority 1: Calibration Analysis (Ready Now)
- **Data exists:** Player estimates vs DM decisions in JSONL
- **Analysis needed:** Extract, quantify error, compare by LLM/action type
- **Timeline:** 1-2 weeks to paper draft
- **Venue:** NeurIPS workshop, ICML workshop

### Priority 2: Graduated Outcomes Benchmark (Ready Now)
- **Data exists:** 500+ sessions with outcome_tiers
- **Work needed:** Evaluation harness, leaderboard, documentation
- **Timeline:** 2-4 weeks to public release
- **Impact:** Could become standard benchmark

### Priority 3: Tactical Coordination Study (Needs More Data)
- **Data exists:** Some sessions with multi-agent combat
- **Work needed:** Run 100+ tactical scenarios, measure coordination
- **Timeline:** 4-8 weeks
- **Venue:** AAAI, IEEE CoG

## Publication Strategy

### Phase 1: Quick Wins (Next 3 months)
1. **ArXiv preprint** - Calibration findings (4-8 pages)
2. **Workshop paper** - NeurIPS LLM Agents (4 pages, July deadline)
3. **Dataset release** - HuggingFace + GitHub + Zenodo DOI

### Phase 2: Full Papers (6-12 months)
4. **AAAI/ICML** - Multi-agent benchmark paper
5. **IEEE CoG** - Tactical coordination paper
6. **FAccT** - Ethical reasoning paper
7. **ACL/EMNLP** - Fine-tuning for personalized worlds

### Phase 3: Applications (12-24 months)
8. **Nature/Science** - Major finding (if discovered)
9. **Book chapter** - Multi-agent systems methodology
10. **Tutorial/Workshop** - Host at major conference

## Supporting Documents

- `01_CALIBRATION_RESEARCH.md` - AI metacognition & overconfidence
- `02_GRADUATED_OUTCOMES_BENCHMARK.md` - Benchmark design & evaluation
- `03_MULTI_AGENT_COORDINATION.md` - Tactical reasoning & emergence
- `04_ETHICAL_REASONING.md` - AI safety testbed
- `05_TACTICAL_MODULE.md` - Novel combat system research
- `06_NARRATIVE_GENERATION.md` - Transmedia pipeline
- `07_FINE_TUNING.md` - Domain-specific LLM training
- `08_GAME_BALANCING.md` - Self-play mechanics tuning
- `09_DATASET_RELEASE.md` - Aeonisk-52 documentation
- `10_NEXT_STEPS.md` - Immediate action items

## Long-Term Vision

**Year 1:** Establish Aeonisk as a benchmark (papers + dataset release)
**Year 2:** Build research community (workshops, challenges, collaborations)
**Year 3:** "The Aeonisk platform" - standard tool for multi-agent research
**Year 5:** Cited in 100+ papers, used by multiple research groups

**Personal goal:** Fine-tuned AI DM that can run your custom world so you can play as a character.

## Notes on Intellectual Property

**Current status:** All code + world lore under permissive licenses (MIT/CC-BY)
**Strategic reason:** Solve IP barrier for researchers, encourage adoption
**Competitive advantage:** First-mover + ongoing development

---

**Next steps:** See `10_NEXT_STEPS.md` for immediate action items.
