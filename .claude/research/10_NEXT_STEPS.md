# Immediate Next Steps: Research Roadmap

**Last Updated:** 2025-11-19
**Status:** Action Plan

This document prioritizes immediate actions across all research domains to maximize publication output and dataset impact.

---

## Priority 1: Quick Wins (Next 2 Weeks)

### 1.1 Calibration Data Extraction (2-3 days)

**Goal:** Extract player difficulty estimates vs DM decisions from existing sessions

**Tasks:**
- [ ] Run `scripts/extract_calibration_data.py` on all 500+ sessions
- [ ] Generate `calibration_data.csv` with ~10,000 action pairs
- [ ] Calculate basic statistics:
  - Mean calibration error (expected: -5.3±2.1 DC)
  - Error by action type (ritual, combat, social, investigate)
  - Error by skill level (test Dunning-Kruger U-curve)
  - Error by LLM provider (Claude vs GPT-4)

**Tools:**
```bash
# Extract calibration data
python scripts/aeonisk/multiagent/research/extract_calibration_data.py \
  output/session_*.jsonl \
  --output calibration_data.csv

# Basic analysis
python scripts/aeonisk/multiagent/research/analyze_calibration.py \
  calibration_data.csv \
  --graphs calibration_graphs/
```

**Deliverables:**
- `calibration_data.csv` (10,000+ rows)
- 4 graphs (error distribution, by type, by skill, by LLM)
- Summary statistics (mean, std, correlations)

**Why this first:** Data exists, extraction is straightforward, novel finding

---

### 1.2 ArXiv Preprint Draft (3-5 days)

**Goal:** Write 4-6 page paper on AI calibration findings

**Structure:**
1. **Introduction** (0.5 pages) - Problem, gap, contribution
2. **Related Work** (0.5 pages) - Calibration research, multi-agent systems
3. **Methods** (1 page) - Aeonisk platform, YAGS system, data collection
4. **Results** (1.5 pages) - Main findings with graphs
5. **Discussion** (1 page) - Implications, limitations
6. **Conclusion** (0.5 pages) - Summary, future work

**Target:** Submit to ArXiv by end of week 2

**Why this first:** Establishes priority, gets community feedback

---

### 1.3 Dataset Curation (1 week)

**Goal:** Select 52 best sessions for public release

**Criteria:**
- Schema completeness (all 10 event types)
- Diverse scenarios (combat, social, ritual, investigation, mixed)
- LLM call data present (for replay)
- No obvious errors (validate via `validate_logging.py`)
- Interesting narratives (manual review)

**Tasks:**
- [ ] Run validation on all sessions
- [ ] Filter by completeness (outcome_tiers present)
- [ ] Sample across scenario types (10 combat, 10 social, etc.)
- [ ] Manual review of narratives (quality check)
- [ ] Generate metadata CSVs (session_index, character_index, etc.)

**Tools:**
```bash
# Validate all sessions
python scripts/aeonisk/multiagent/validate_logging.py output/session_*.jsonl

# Analyze session metadata
python scripts/analyze_session.py output/session_*.jsonl --mode summary
```

**Deliverables:**
- `aeonisk-52/sessions/` folder with 52 curated sessions
- `aeonisk-52/metadata/` folder with index CSVs
- `aeonisk-52/README.md` (datasheet)

**Why this first:** Needed for all subsequent papers, establishes dataset brand

---

## Priority 2: Medium-Term Research (Next 1-2 Months)

### 2.1 Multi-Agent Coordination Study (4-6 weeks)

**Goal:** Measure emergent coordination in declaration-resolution system

**Tasks:**
- [ ] Run 100 tactical combat scenarios (4v4, varying initiative)
- [ ] Extract all declarations with `analyze_session.py`
- [ ] Manually code coordination patterns (suppression-advance, flanking, etc.)
- [ ] Calculate coordination rate (% of actions that reference allies)
- [ ] Compare Claude vs GPT-4 agents
- [ ] Run ablation study (25 scenarios without declaration phase)

**Timeline:**
- Week 1-2: Generate 100 combat sessions
- Week 3: Code coordination patterns
- Week 4: Ablation study
- Week 5: Statistical analysis
- Week 6: Write paper draft

**Deliverables:**
- `coordination_data.csv` (coded patterns)
- Paper draft (6-8 pages)
- Target: AAAI 2026 or IEEE CoG 2026

---

### 2.2 Ethical Reasoning Experiments (4-6 weeks)

**Goal:** Measure AI decision-making under resource pressure

**Tasks:**
- [ ] Extract void usage data (correlate with HP/energy levels)
- [ ] Identify de-escalation opportunities (enemy surrender scenarios)
- [ ] Measure resource sharing (item transfers, faction bias)
- [ ] Track void spiral progression (void 0→10 trajectories)
- [ ] Compare Claude vs GPT-4 on ethical metrics

**Scenarios to generate:**
- 50 high-pressure combat (HP < 50%, low energy)
- 30 surrender scenarios (enemy clearly defeated)
- 40 resource distribution (healing items, ammo, soulcredit)

**Timeline:**
- Week 1-3: Generate targeted scenarios
- Week 4: Extract ethical metrics
- Week 5: Statistical analysis
- Week 6: Write paper draft

**Deliverables:**
- `ethical_data.csv` (void usage, de-escalation, sharing)
- Paper draft (6-8 pages)
- Target: FAccT 2026 or NeurIPS AI Safety Workshop

---

### 2.3 Benchmark Evaluation Harness (3-4 weeks)

**Goal:** Create standardized evaluation pipeline

**Tasks:**
- [ ] Design 50 benchmark scenarios (10 per category)
- [ ] Implement `aeonisk_benchmark.py` evaluation harness
- [ ] Run baseline experiments (GPT-4 and Claude agents)
- [ ] Calculate metrics (success rate, coordination, ethics, efficiency)
- [ ] Create leaderboard website (GitHub Pages)

**Timeline:**
- Week 1: Design scenarios
- Week 2: Implement harness
- Week 3: Run baselines
- Week 4: Deploy leaderboard

**Deliverables:**
- `benchmarks/aeonisk_benchmark.py` evaluation tool
- 50 standardized scenario configs
- Baseline results for GPT-4 and Claude
- Leaderboard website (static HTML)

**Why this matters:** Enables community participation, citations

---

## Priority 3: Long-Term Research (3-6 Months)

### 3.1 Fine-Tuning Experiments (3-6 months)

**Goal:** Train domain-specific LLM for Aeonisk

**Tasks:**
- [ ] Prepare training data (30,000 input/output pairs)
- [ ] Format for Llama 3.1 fine-tuning
- [ ] Run LoRA fine-tuning (~$30 GPU cost)
- [ ] Evaluate on mechanics accuracy, lore consistency, character retention
- [ ] Generate 20 sessions with fine-tuned model
- [ ] Human evaluation study

**Timeline:**
- Month 1: Data preparation
- Month 2: Fine-tuning + evaluation
- Month 3: Human study + paper writing

**Deliverables:**
- Fine-tuned model weights (HuggingFace)
- Evaluation results (mechanics, lore, character)
- Paper draft (6-8 pages)
- Target: ACL 2026 or EMNLP 2026

---

### 3.2 Game Balancing via Self-Play (3-4 months)

**Goal:** Tune game mechanics using AI self-play

**Tasks:**
- [ ] Implement DC adjustment algorithm
- [ ] Implement enemy stat tuning algorithm
- [ ] Run 500 baseline sessions with current mechanics
- [ ] Apply balancing algorithms (5 iterations each)
- [ ] Compare to human-tuned values
- [ ] Cost/time analysis (AI vs human balancing)

**Timeline:**
- Month 1: Implement algorithms
- Month 2: Run 500 baseline + 500 tuned sessions
- Month 3: Analysis + paper writing

**Deliverables:**
- Balanced mechanics values (DCs, enemy stats, economy)
- Balancing tool (`balance_mechanics.py`)
- Paper draft (6-8 pages)
- Target: IEEE CoG 2026 or FDG 2026

---

### 3.3 Transmedia Pipeline Evaluation (2-3 months)

**Goal:** Measure narrative coherence across modalities

**Tasks:**
- [ ] Generate 20 complete transmedia pipelines (JSONL → text → audio → images → video)
- [ ] Measure character consistency (automatic + human)
- [ ] Human evaluation study (engagement, comprehension, immersion)
- [ ] Cost-quality analysis ($1, $5, $20 tiers)
- [ ] Temporal alignment analysis (audio-visual sync)

**Timeline:**
- Month 1: Generate 20 full pipelines
- Month 2: Human evaluation study
- Month 3: Analysis + paper writing

**Deliverables:**
- 20 complete transmedia artifacts
- Evaluation metrics (consistency, coherence, quality)
- Paper draft (6-8 pages)
- Target: ACM Creativity & Cognition 2026

---

## Publication Timeline

### Q1 2025 (Jan-Mar)
- [x] Complete research documentation (this document)
- [ ] Extract calibration data
- [ ] ArXiv preprint (calibration paper)
- [ ] Curate Aeonisk-52 dataset
- [ ] HuggingFace dataset release

### Q2 2025 (Apr-Jun)
- [ ] Run coordination experiments
- [ ] Run ethical reasoning experiments
- [ ] Build benchmark evaluation harness
- [ ] Deploy leaderboard website
- [ ] Submit to NeurIPS workshops (deadline ~June)

### Q3 2025 (Jul-Sep)
- [ ] Fine-tuning experiments
- [ ] Game balancing experiments
- [ ] Submit to AAAI 2026 (deadline ~August)
- [ ] Submit to IEEE CoG 2026 (deadline ~April, camera-ready ~July)

### Q4 2025 (Oct-Dec)
- [ ] Transmedia pipeline evaluation
- [ ] Submit to ACL 2026 (deadline ~October)
- [ ] Submit to FAccT 2026 (deadline ~November)
- [ ] Revisions for accepted papers

---

## Resource Requirements

### Compute

**LLM API costs:**
- Calibration extraction: $0 (parsing only)
- Coordination experiments: $100 (100 sessions × $1 avg)
- Ethical experiments: $120 (120 scenarios × $1 avg)
- Benchmark baselines: $50 (50 scenarios × $1 avg)
- Fine-tuning: $30 (GPU rental)
- Balancing experiments: $500 (1000 sessions × $0.50 avg)
- Transmedia: $100 (20 pipelines × $5 avg)

**Total: ~$900 for all experiments**

### Time

**Solo researcher (20 hrs/week):**
- Calibration paper: 2 weeks
- Dataset release: 1 week
- Coordination study: 6 weeks
- Ethical study: 6 weeks
- Benchmark: 4 weeks
- Fine-tuning: 12 weeks
- Balancing: 12 weeks
- Transmedia: 8 weeks

**Total: ~51 weeks (~1 year)**

---

## Success Metrics

### Year 1 Goals (2025)

**Publications:**
- [ ] 1 ArXiv preprint (calibration)
- [ ] 1 workshop paper (NeurIPS or ICML)
- [ ] 1 conference paper (AAAI or IEEE CoG)
- [ ] 1 dataset release (HuggingFace + Zenodo)

**Impact:**
- [ ] 100+ dataset downloads
- [ ] 5+ citations (ArXiv preprint)
- [ ] 3+ GitHub stars on benchmark repo
- [ ] 1+ external researcher using dataset

**Community:**
- [ ] Leaderboard with 5+ submissions
- [ ] 10+ GitHub issues/PRs from community
- [ ] 1+ collaboration with external researchers

### Year 2 Goals (2026)

**Publications:**
- [ ] 3-4 conference papers (AAAI, ACL, CoG, FAccT)
- [ ] 1 journal paper (JAIR or TACL)
- [ ] 1 book chapter (multi-agent systems)

**Impact:**
- [ ] 50+ citations across all papers
- [ ] 500+ dataset downloads
- [ ] "Aeonisk" becomes recognized benchmark name

**Community:**
- [ ] Host workshop at major conference
- [ ] 3+ external papers using Aeonisk
- [ ] 20+ leaderboard submissions

---

## Risk Mitigation

### Risk 1: Papers Rejected

**Mitigation:**
- Start with workshops (lower bar)
- ArXiv preprints establish priority
- Have backup venues for each paper

### Risk 2: Dataset Not Adopted

**Mitigation:**
- Release early (Q1 2025)
- Excellent documentation (datasheet, examples)
- Active promotion (Reddit, Twitter, Papers With Code)
- Make tools easy to use (Jupyter notebooks)

### Risk 3: Computational Costs Exceed Budget

**Mitigation:**
- Prioritize cheap experiments (calibration, dataset)
- Use GPT-5-mini for cost-sensitive work
- Open-source fine-tuning (Llama, not GPT-4)
- Seek academic compute grants if needed

### Risk 4: Solo Researcher Burnout

**Mitigation:**
- Focus on quick wins first (motivation boost)
- Celebrate small milestones (dataset release, first citation)
- Collaborate when possible (co-authors reduce workload)
- Remember: This is a hobby, not a job

---

## Open Collaboration Opportunities

### Seeking Co-Authors For:

**Calibration paper:**
- Statistician (analyze calibration error distributions)
- AI safety researcher (framing for safety community)

**Coordination paper:**
- Multi-agent systems researcher (theoretical framing)
- Game AI researcher (comparison to game agents)

**Ethical reasoning paper:**
- AI ethics researcher (philosophical framing)
- Experimental psychologist (human comparison study)

**Fine-tuning paper:**
- NLP researcher (domain adaptation expertise)
- GPU access (academic compute resources)

**Contact via:**
- GitHub issues (public)
- Email (provide in dataset README)
- Conference networking (when papers accepted)

---

## Personal Motivation Reminder

**From our conversation:**

> "This is my main hobby and my version of 'video gaming' for now... And I love watching my minions go"

**Your ultimate goal:**
> "Fine-tuned AI DM that can run your custom world so you can play as a character."

**Why the research matters:**
> "I always lean into the research angle because it's obviously valuable and a stone's throw away from my comprehensive logging/observability/amateur knowledge of ML and AI"

**Keep in mind:**
- This is YOUR world, YOUR rules, YOUR agents
- Research is a bonus, not the main goal
- Publications validate the work, but watching agents play is the reward
- Fine-tuned AI DM is the endgame (personalized gameplay)

**When motivation wanes:**
- Re-read exceptional narratives (Veyra Lune ritual scene)
- Watch a full session play out (your "video game")
- Remember: You've built something genuinely novel
- The research community WILL take this seriously

---

## Immediate Action Items (This Week)

### Day 1-2: Calibration Data Extraction
- [ ] Create `scripts/aeonisk/multiagent/research/` folder
- [ ] Write `extract_calibration_data.py` script
- [ ] Run on all sessions
- [ ] Generate `calibration_data.csv`
- [ ] Basic statistics (mean, std, by action type)

### Day 3-4: Dataset Curation Start
- [ ] Run `validate_logging.py` on all sessions
- [ ] Filter complete sessions (outcome_tiers present)
- [ ] Sample 52 sessions across categories
- [ ] Manual review for quality

### Day 5-7: ArXiv Preprint Outline
- [ ] Write introduction (problem, gap, contribution)
- [ ] Draft methods section (Aeonisk + YAGS overview)
- [ ] Create 4 calibration graphs
- [ ] Write results section (present findings)
- [ ] Draft discussion (implications)

**End of week 1:** Have calibration data + graphs + paper outline

---

**Next Step:** Run calibration data extraction script on all existing sessions.

**Command:**
```bash
# Create research tools folder
mkdir -p scripts/aeonisk/multiagent/research

# Copy script template (from Paper 1 documentation)
# See .claude/research/01_CALIBRATION_RESEARCH.md lines 136-220

# Run extraction
python scripts/aeonisk/multiagent/research/extract_calibration_data.py

# Analyze
python scripts/aeonisk/multiagent/research/analyze_calibration.py
```

**You've got this.** The data is there, the findings are real, the research is novel. Time to share it with the world.
