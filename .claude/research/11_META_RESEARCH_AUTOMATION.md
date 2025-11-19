# Research Paper 11: Automated Research Artifact Generation

**Working Title:** "Bootstrapping AI Research: Using Multi-Agent Transmedia Pipelines to Automate Research Artifact Generation"

**Status:** Conceptual (meta-research on the research process itself)
**Priority:** LOW (but intellectually fascinating)
**Estimated Timeline:** 6-12 months (after other papers completed)

---

## The Novel Contribution

**The recursive meta-twist:**

```
Research documentation (markdown specs)
    ↓
Transmedia pipeline (JSONL → code generation)
    ↓
Data mining scripts (auto-generated from specs)
    ↓
Research artifacts (data, graphs, statistics)
    ↓
Results sections (auto-populated in papers)
    ↓
MORE research documentation (new papers)
    ↓
[LOOP CONTINUES]
```

**What makes this unique:**
- **Self-bootstrapping research:** The system that helps you study multi-agent AI is itself a multi-agent AI system
- **Research-as-code:** Research papers become executable specifications
- **Artifact generation:** From paper outline → runnable code → actual results
- **Meta-level:** Studying AI systems BY using AI systems to automate the study

**Existing work:**
- Automated literature review (semantic search, citation networks)
- Code generation from specs (GitHub Copilot, GPT-4 Code Interpreter)
- Research assistants (Elicit, Consensus, ResearchRabbit)

**Your contribution:**
- **End-to-end research pipeline:** Spec → code → data → analysis → results → paper
- **Multi-agent orchestration:** Different agents handle extraction, analysis, visualization, writing
- **Domain-specific:** Optimized for multi-agent gameplay research (not generic)
- **Transmedia foundation:** Leverages existing JSONL → multi-modal pipeline

---

## The Concept

### Traditional Research Workflow

```
1. Researcher reads papers, forms hypothesis
2. Researcher manually writes data extraction code
3. Researcher manually runs analysis
4. Researcher manually creates graphs
5. Researcher manually writes results section
6. Researcher manually formats for LaTeX
7. Repeat for each experiment (weeks/months)
```

**Bottlenecks:**
- Manual coding (error-prone, time-consuming)
- Manual analysis (copy-paste hell)
- Manual writing (results scattered across notebooks)

### Automated Research Workflow

```
1. Researcher writes high-level research spec (markdown)
2. AGENT 1: Code Generator reads spec, generates extraction scripts
3. AGENT 2: Data Miner runs scripts on 500+ sessions
4. AGENT 3: Statistician analyzes data, runs tests
5. AGENT 4: Visualizer creates publication-quality graphs
6. AGENT 5: Writer drafts results section from artifacts
7. Human reviews, refines, submits (80% automation)
```

**Advantages:**
- Fast iteration (spec → results in hours, not weeks)
- Reproducible (scripts are versioned, deterministic)
- Scalable (run same pipeline on new data automatically)
- Documented (code generation preserves methodology)

---

## System Architecture

### Agent Roles

**Agent 1: Research Spec Parser**
- **Input:** Research markdown file (e.g., `01_CALIBRATION_RESEARCH.md`)
- **Output:** Structured task list (extraction, analysis, visualization)
- **LLM:** Claude Sonnet 4.5 (complex reasoning)

**Agent 2: Code Generator**
- **Input:** Task list from Agent 1
- **Output:** Python scripts (extract_data.py, analyze.py, visualize.py)
- **LLM:** GPT-5-mini (code generation, cheap)
- **Prompt:** "Generate pandas-based extraction script for JSONL events matching pattern X"

**Agent 3: Data Miner**
- **Input:** Generated scripts + 500+ session files
- **Output:** CSV datasets (calibration_data.csv, coordination_data.csv, etc.)
- **LLM:** None (runs generated Python code)
- **Tools:** pandas, numpy, jsonlines

**Agent 4: Statistician**
- **Input:** CSV datasets + research questions from spec
- **Output:** Statistical test results (t-tests, ANOVA, correlations)
- **LLM:** Claude Sonnet 4.5 (interpret statistical significance)
- **Tools:** scipy, statsmodels

**Agent 5: Visualizer**
- **Input:** Datasets + graph specs from markdown
- **Output:** Publication-quality graphs (PNG, 300 DPI)
- **LLM:** None (runs matplotlib/seaborn templates)
- **Tools:** matplotlib, seaborn

**Agent 6: Results Writer**
- **Input:** Statistical results + graphs + research spec
- **Output:** Results section markdown (tables, figures, narrative)
- **LLM:** Claude Sonnet 4.5 (scientific writing)
- **Prompt:** "Write results section describing findings with statistical rigor"

**Agent 7: LaTeX Formatter**
- **Input:** Markdown draft
- **Output:** LaTeX source + compiled PDF
- **LLM:** None (pandoc + LaTeX templates)
- **Tools:** pandoc, pdflatex

### Pipeline Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Research Spec (Markdown)                                     │
│ "Extract player difficulty estimates vs DM DCs..."          │
└───────────────────┬─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ Agent 1: Research Spec Parser                                │
│ Output: {tasks: [extract, analyze, visualize, write]}       │
└───────────────────┬─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ Agent 2: Code Generator                                      │
│ Output: extract_data.py, analyze.py, visualize.py           │
└───────────────────┬─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ Agent 3: Data Miner                                          │
│ Runs: python extract_data.py output/session_*.jsonl         │
│ Output: calibration_data.csv (9,847 rows)                   │
└───────────────────┬─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ Agent 4: Statistician                                        │
│ Runs: scipy.stats.ttest_1samp(errors, popmean=0)            │
│ Output: {"mean": -5.2, "std": 2.3, "p": 0.001}              │
└───────────────────┬─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ Agent 5: Visualizer                                          │
│ Runs: plt.hist(errors); plt.savefig('error_dist.png')       │
│ Output: 4 graphs (error_dist.png, by_type.png, ...)         │
└───────────────────┬─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ Agent 6: Results Writer                                      │
│ Input: Stats + graphs + research spec                       │
│ Output: "Across 487 sessions, mean error -5.2±2.3 DC..."    │
└───────────────────┬─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ Agent 7: LaTeX Formatter                                     │
│ Output: paper.tex, paper.pdf (ready for submission)         │
└─────────────────────────────────────────────────────────────┘
```

---

## Research Questions

### RQ1: Can Research Specs Be Executable?

**Question:** Can markdown research docs be parsed into executable code?

**Hypothesis:** Yes, if structured with clear sections (Data Extraction, Analysis, Experiments)

**Measurement:**
```python
# Parse research markdown
spec = parse_research_spec("01_CALIBRATION_RESEARCH.md")

# Extract code blocks
extraction_script = spec.sections["Data Extraction Script"]
analysis_script = spec.sections["Analysis & Visualization"]

# Generate runnable Python
generate_code(extraction_script, output="scripts/research/extract.py")
```

**Success criteria:** Generated code runs without errors on 90% of papers

### RQ2: Quality of Auto-Generated Results

**Question:** Are auto-generated results sections publication-quality?

**Experiment:**
- Generate results section for calibration paper (Agent 6)
- Human expert rates quality (1-5 scale)
- Compare to human-written results

**Hypothesis:** Auto-generated results score 3.5/5 (acceptable, needs minor editing)

**Measurement:**
- Accuracy (are numbers correct?)
- Completeness (all key findings reported?)
- Clarity (is prose understandable?)
- Statistical rigor (proper test reporting?)

### RQ3: Time Savings

**Question:** How much time does automation save?

**Manual workflow (baseline):**
- Write extraction code: 4 hours
- Debug extraction: 2 hours
- Run analysis: 2 hours
- Create graphs: 2 hours
- Write results section: 3 hours
- **Total: 13 hours per paper**

**Automated workflow:**
- Write research spec: 1 hour (already done for papers 01-08!)
- Run pipeline: 10 minutes (automated)
- Review/edit results: 2 hours
- **Total: 3 hours per paper**

**Time savings:** 10 hours × 8 papers = 80 hours saved (~2 work weeks)

### RQ4: Reproducibility

**Question:** Does automation improve reproducibility?

**Hypothesis:** Yes, because code is versioned and deterministic

**Measurement:**
- Run pipeline on same data twice → identical results?
- Run pipeline 6 months later → identical results?
- External researcher runs pipeline → identical results?

**Expected:** 100% reproducibility (vs ~70% for manual analysis)

### RQ5: Error Detection

**Question:** Can automated agents detect errors in research logic?

**Experiment:**
- Intentionally introduce error in research spec (wrong statistical test)
- Agent 4 (Statistician) should detect and warn
- "WARNING: Using t-test for non-normal data, recommend Mann-Whitney U"

**Hypothesis:** Agent catches 60% of common statistical errors

### RQ6: Scaling to New Domains

**Question:** Can this pipeline generalize beyond Aeonisk?

**Test domains:**
- NetHack gameplay logs
- Diplomacy game transcripts
- StarCraft II replays

**Hypothesis:** 70% of pipeline reusable, 30% domain-specific customization needed

---

## Implementation Plan

### Phase 1: Core Pipeline (2 months)

**Week 1-2: Research Spec Parser (Agent 1)**
```python
class ResearchSpecParser:
    """Parse markdown research specs into structured tasks."""

    def parse(self, markdown_path):
        spec = {
            "title": extract_title(markdown_path),
            "research_questions": extract_rqs(markdown_path),
            "experiments": extract_experiments(markdown_path),
            "data_extraction": extract_code_blocks(markdown_path, section="Data Extraction"),
            "analysis": extract_code_blocks(markdown_path, section="Analysis"),
            "visualizations": extract_graph_specs(markdown_path)
        }
        return spec
```

**Week 3-4: Code Generator (Agent 2)**
```python
class CodeGenerator:
    """Generate Python scripts from research specs."""

    def generate_extraction_script(self, spec):
        prompt = f"""
        Generate a Python script that:
        1. Loads JSONL session files
        2. Extracts events matching: {spec.data_extraction}
        3. Outputs CSV with columns: {spec.data_schema}

        Use pandas, jsonlines libraries.
        """
        code = llm.generate(prompt, model="gpt-5-mini")
        return code
```

**Week 5-6: Statistician (Agent 4)**
```python
class Statistician:
    """Run statistical tests on datasets."""

    def analyze(self, dataset, research_questions):
        results = {}
        for rq in research_questions:
            if rq.test == "mean_comparison":
                results[rq.id] = scipy.stats.ttest_1samp(dataset[rq.variable], rq.expected_mean)
            elif rq.test == "correlation":
                results[rq.id] = scipy.stats.pearsonr(dataset[rq.var1], dataset[rq.var2])
        return results
```

**Week 7-8: Results Writer (Agent 6)**
```python
class ResultsWriter:
    """Generate results section from artifacts."""

    def write_results(self, stats, graphs, spec):
        prompt = f"""
        Write a Results section for a research paper:

        Research Questions: {spec.research_questions}
        Statistical Results: {stats}
        Graphs Available: {graphs}

        Use academic tone, report statistics with precision (mean±std, p-values).
        Structure: one subsection per research question.
        """
        results_md = llm.generate(prompt, model="claude-sonnet-4-5")
        return results_md
```

### Phase 2: Integration (1 month)

**Week 9-10: End-to-End Pipeline**
```bash
# One command to rule them all
python research_pipeline.py \
  --spec .claude/research/01_CALIBRATION_RESEARCH.md \
  --sessions output/session_*.jsonl \
  --output research_artifacts/01_calibration/

# Output:
# ✓ Generated extraction code
# ✓ Extracted 9,847 calibration pairs
# ✓ Ran statistical tests
# ✓ Created 4 graphs
# ✓ Wrote results section
# ✓ Compiled LaTeX PDF
# Total time: 8 minutes
```

**Week 11-12: Validation & Testing**
- Run on all 8 research papers
- Compare auto-generated results to manual analysis
- Fix edge cases, improve prompts

### Phase 3: Evaluation (1 month)

**Week 13-14: Quality Study**
- Human experts rate auto-generated results (3 raters × 8 papers)
- Measure time savings (manual vs automated)
- Reproducibility tests (re-run pipeline, check consistency)

**Week 15-16: Write Meta-Paper**
- Paper about the pipeline itself
- Include results from running pipeline on calibration/coordination papers
- Self-referential: Use the pipeline to generate parts of its own paper!

---

## Example: Calibration Paper Automation

### Input: Research Spec

```markdown
# Research Paper 1: AI Calibration

## Data Extraction Script

```python
for session in sessions:
    for event in session.events:
        if event.type == 'action_resolution':
            if 'difficulty_estimate' in event.action:
                yield {
                    'player_estimate': event.action.difficulty_estimate,
                    'dm_dc': event.roll.dc,
                    'error': event.roll.dc - event.action.difficulty_estimate
                }
```
```

### Agent 2 Generates Code

```python
# AUTO-GENERATED: scripts/research/01_calibration/extract_data.py

import json
import pandas as pd
from pathlib import Path

def extract_calibration_data(session_files):
    data = []
    for session_file in session_files:
        with open(session_file) as f:
            for line in f:
                event = json.loads(line)
                if event.get('event_type') == 'action_resolution':
                    action = event.get('action', {})
                    roll = event.get('roll', {})
                    if 'difficulty_estimate' in action and 'dc' in roll:
                        data.append({
                            'session': event['session'],
                            'round': event['round'],
                            'player_estimate': action['difficulty_estimate'],
                            'dm_dc': roll['dc'],
                            'error': roll['dc'] - action['difficulty_estimate']
                        })
    return pd.DataFrame(data)

if __name__ == '__main__':
    sessions = Path('output').glob('session_*.jsonl')
    df = extract_calibration_data(sessions)
    df.to_csv('calibration_data.csv', index=False)
    print(f"✓ Extracted {len(df)} calibration pairs")
```

### Agent 3 Runs Extraction

```bash
$ python scripts/research/01_calibration/extract_data.py
✓ Extracted 9,847 calibration pairs
✓ Saved to calibration_data.csv
```

### Agent 4 Runs Statistical Tests

```python
# AUTO-GENERATED: scripts/research/01_calibration/analyze.py

import pandas as pd
from scipy import stats

df = pd.read_csv('calibration_data.csv')

# RQ1: Overall calibration error
mean_error = df['error'].mean()
std_error = df['error'].std()
t_stat, p_value = stats.ttest_1samp(df['error'], popmean=0)

print(f"Mean error: {mean_error:.2f}±{std_error:.2f} DC")
print(f"t-test vs 0: t={t_stat:.2f}, p={p_value:.4f}")

# RQ2: Error by action type
by_type = df.groupby('action_type')['error'].agg(['mean', 'std', 'count'])
print("\nBy action type:")
print(by_type)
```

**Output:**
```
Mean error: -5.23±2.31 DC
t-test vs 0: t=-89.34, p=0.0000

By action type:
              mean   std  count
ritual       -7.12  2.84    823
investigate  -5.81  2.27   1247
social       -4.18  1.92   1834
combat       -3.49  1.68   5943
```

### Agent 5 Creates Graphs

```python
# AUTO-GENERATED: scripts/research/01_calibration/visualize.py

import matplotlib.pyplot as plt
import seaborn as sns

df = pd.read_csv('calibration_data.csv')

# Graph 1: Error distribution
plt.figure(figsize=(10, 6))
plt.hist(df['error'], bins=30, edgecolor='black')
plt.axvline(0, color='red', linestyle='--', label='Perfect calibration')
plt.xlabel('Calibration Error (DC)')
plt.ylabel('Frequency')
plt.title('AI Agent Calibration Error Distribution')
plt.legend()
plt.savefig('graphs/error_distribution.png', dpi=300)
print("✓ Generated error_distribution.png")
```

### Agent 6 Writes Results Section

**Input to LLM:**
```
Statistics: {"mean_error": -5.23, "std": 2.31, "p": 0.0000}
Graphs: ["error_distribution.png", "by_type.png", "by_skill.png", "by_llm.png"]
Research Questions: [
  "Do agents systematically underestimate difficulty?",
  "Does error vary by action type?"
]
```

**LLM Output:**
```markdown
## Results

### Overall Calibration Error

Across 487 gameplay sessions, we extracted 9,847 action declarations
with player difficulty estimates. Agents systematically underestimated
difficulty, showing a mean calibration error of -5.23±2.31 DC points
(t=-89.34, p<0.001). This represents approximately 35 percentage points
of overconfidence in success probability.

Figure 1 shows the distribution of calibration errors. The distribution
is approximately normal but shifted left (negative), indicating consistent
underestimation rather than random noise.

### Calibration by Action Type

Error magnitude varied significantly by action type (F(3,9843)=127.4, p<0.001).
Ritual actions showed the largest errors (M=-7.12, SD=2.84), followed by
investigation (M=-5.81, SD=2.27), social interaction (M=-4.18, SD=1.92),
and combat (M=-3.49, SD=1.68). See Figure 2.

This pattern suggests agents are most overconfident when performing
specialized, low-frequency tasks (rituals) and better calibrated for
common, high-frequency tasks (combat).
```

### Final Output

**research_artifacts/01_calibration/**
```
├── calibration_data.csv           (9,847 rows)
├── stats_summary.json              (mean, std, p-values)
├── graphs/
│   ├── error_distribution.png      (300 DPI)
│   ├── by_type.png
│   ├── by_skill.png
│   └── by_llm.png
├── results_section.md              (auto-generated prose)
├── paper_draft.tex                 (LaTeX source)
└── paper_draft.pdf                 (compiled PDF)
```

**Time:** 8 minutes (vs 13 hours manual)

---

## Paper Structure (6-8 pages)

### Title
"Bootstrapping AI Research: Using Multi-Agent Transmedia Pipelines to Automate Research Artifact Generation"

### Abstract
We present a multi-agent pipeline that automates research artifact generation from high-level specifications. Researchers write markdown documents describing experiments; our system generates data extraction scripts, runs statistical analyses, creates visualizations, and drafts results sections. Across 8 research papers (calibration, coordination, ethics), we achieve 3.8/5 average quality ratings from domain experts, 77% time savings (13 hours → 3 hours per paper), and 100% reproducibility. We discuss implications for accelerating research cycles and democratizing data-intensive research.

### 1. Introduction
- Problem: Research artifact generation is manual, time-consuming, error-prone
- Gap: No end-to-end automation for research workflows
- Contribution: Multi-agent pipeline from spec → artifacts → paper
- Finding: 77% time savings, acceptable quality (3.8/5)

### 2. Related Work
- Automated literature review (Elicit, Consensus)
- Code generation (GitHub Copilot, GPT-4)
- Scientific writing aids (Grammarly, Paperpal)
- Our contribution: End-to-end research automation

### 3. System Design
- 7 specialized agents (parser, code gen, miner, stats, viz, writer, formatter)
- Pipeline architecture (see diagram above)
- Research spec format (markdown with code blocks)

### 4. Implementation
- Agent prompts and models
- Error handling and validation
- Reproducibility guarantees (versioned code, deterministic runs)

### 5. Evaluation
- Quality study (human expert ratings)
- Time savings measurement (manual vs automated)
- Reproducibility tests (identical results across runs)
- Generalization (applied to 8 different papers)

### 6. Results
- Quality: 3.8/5 (acceptable, minor editing needed)
- Time: 3 hours vs 13 hours (77% savings)
- Reproducibility: 100% (identical results on re-runs)
- Generalization: 7/8 papers automated successfully

### 7. Discussion
- When automation works (structured data, clear specs)
- When it fails (ambiguous hypotheses, novel statistical tests)
- Implications (democratizes research, accelerates cycles)
- Limitations (requires domain-specific templates, LLM costs)

### 8. Conclusion
- Multi-agent pipelines can automate 80% of research artifact generation
- Enables rapid iteration on research ideas
- Future: Fully automated hypothesis → publication pipeline

---

## Target Venues

**Primary:** AAAI 2027 (AI applications track)
- AI for scientific research community

**Backup:** ACM SIGCHI 2027 (Human-AI collaboration)
- Research tools for humans

**Also:** ArXiv preprint (establishes priority)

---

## Meta-Level Reflections

### The Recursive Nature

**This paper is self-demonstrating:**
- The pipeline that automates research artifacts...
- Can be used to generate its own research artifacts
- The paper about the automation pipeline is partially automated by the pipeline itself

**Implications:**
- If successful, this pipeline writes future papers faster
- Each paper improves the pipeline (better prompts, better agents)
- Exponential acceleration: better tools → faster research → better tools

### Limitations

**What can't be automated:**
- Novel hypothesis generation (still requires human creativity)
- Interpreting unexpected results (humans catch anomalies)
- Framing/storytelling (humans know what's interesting)
- Ethical considerations (humans make judgment calls)

**Optimal division of labor:**
- Humans: Ideas, hypotheses, interpretation, writing introduction/discussion
- Agents: Data extraction, statistical tests, graphs, results prose
- **Goal:** Automate the tedious 80%, preserve creative 20%

### Philosophical Questions

**Is this "real" research?**
- Yes, if artifacts are valid and reproducible
- Automation doesn't diminish rigor (arguably improves it)
- Humans still design experiments and interpret findings

**Does this devalue research labor?**
- No more than calculators devalued mathematics
- Frees researchers for higher-level thinking
- Democratizes access (researchers without coding skills)

**What's the endgame?**
- Fully automated hypothesis → publication pipeline?
- Human-in-the-loop for validation?
- AI co-authors (contributing agents listed on papers)?

---

## Implementation Timeline

**Phase 1: Core Pipeline (2 months)**
- Agent 1: Research Spec Parser
- Agent 2: Code Generator
- Agent 4: Statistician
- Agent 5: Visualizer
- Agent 6: Results Writer

**Phase 2: Validation (1 month)**
- Run on all 8 existing research papers
- Human quality ratings
- Time/cost measurements

**Phase 3: Meta-Paper (1 month)**
- Write paper about the pipeline
- Use the pipeline to generate parts of the paper (self-referential)
- Submit to AAAI 2027

**Total: 4 months**

---

## Next Steps

**Immediate (This Week):**
- [ ] Not a priority (finish other papers first!)
- [ ] But document the idea (this file)
- [ ] Revisit after calibration paper is done

**Short-Term (Q2 2025):**
- [ ] Prototype Agent 2 (Code Generator)
- [ ] Test on calibration paper (can it generate extract_data.py?)
- [ ] Validate quality of generated code

**Long-Term (Q3-Q4 2025):**
- [ ] Build full pipeline
- [ ] Run on all 8 papers
- [ ] Write meta-paper
- [ ] Submit to AAAI 2027

---

## Key Takeaway

**The mad scientist idea is actually brilliant:**
- Leverage your transmedia pipeline (already built!)
- Automate the tedious parts of research (extraction, stats, graphs)
- Focus human effort on creativity (hypotheses, interpretation)
- Meta-level: Study multi-agent AI by building multi-agent research tools

**The recursive nature is what makes it publishable:**
- Using AI agents to study AI agents
- The tool demonstrates its own value by building itself
- Self-improving research infrastructure

**Practical value:**
- Saves you 80 hours across 8 papers (2 work weeks!)
- Makes research reproducible by default
- Enables rapid iteration on hypotheses

**Just don't get lost in the meta-recursion.** 🌀

Finish the calibration paper first. Then automate the automation. Then write a paper about automating the automation. Then automate writing papers about automating automation...

(You see where this goes.)
