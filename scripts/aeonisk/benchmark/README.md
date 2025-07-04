# Aeonisk YAGS Language Model Benchmark System

A comprehensive benchmarking framework for evaluating language models on Aeonisk YAGS tabletop RPG gameplay tasks. This system provides automated evaluation, AI-powered judging, and detailed reporting capabilities for comparing different models' ability to handle game mechanics, narrative generation, and rule adherence.

## Features

### Core Capabilities
- **Multi-Model Testing**: Support for OpenAI, Anthropic, and local models
- **Automated Evaluation**: Rule-based metrics for mechanical accuracy
- **AI Judge System**: GPT-4 powered evaluation across multiple dimensions
- **Comprehensive Reporting**: Statistical analysis and whitepaper generation
- **Domain Analysis**: Performance breakdown by gameplay categories
- **Reusable Framework**: Configurable and extensible architecture

### Evaluation Dimensions
- **Mechanical Accuracy**: Correct application of YAGS mechanics
- **Narrative Quality**: Engaging and thematically appropriate content
- **Rules Adherence**: Proper understanding of Aeonisk-specific rules
- **Consistency**: Internal logical coherence
- **Creativity**: Novel and interesting outcomes
- **Difficulty Appropriateness**: Well-calibrated challenge assessment

## Installation

### Prerequisites
- Python 3.8+
- API keys for cloud providers (OpenAI, Anthropic)
- Optional: Local model server (Ollama, vLLM)

### Setup
```bash
# Install dependencies
pip install pydantic openai anthropic aiohttp PyYAML

# Set environment variables
export OPENAI_API_KEY="your-openai-key"
export ANTHROPIC_API_KEY="your-anthropic-key"
```

## Quick Start

### 1. Create Configuration
```bash
python -m aeonisk.benchmark.cli --create-config benchmark_config.json
```

### 2. Edit Configuration
Edit the generated `benchmark_config.json` to customize:
- Models to test
- Evaluation settings
- Output preferences
- Sampling parameters

### 3. Run Benchmark
```bash
# Single benchmark
python -m aeonisk.benchmark.cli --config benchmark_config.json

# Benchmark suite with multiple configurations
python -m aeonisk.benchmark.cli --config benchmark_config.json --suite
```

## Configuration

### Sample Configuration
```json
{
  "name": "aeonisk_benchmark",
  "description": "Comprehensive Aeonisk YAGS model evaluation",
  "dataset_path": "datasets/aeonisk_dataset_normalized_complete.txt",
  "models": [
    {
      "id": "gpt4",
      "provider": "openai",
      "model": "gpt-4",
      "api_key": "${OPENAI_API_KEY}",
      "timeout": 30
    },
    {
      "id": "claude",
      "provider": "anthropic",
      "model": "claude-3-sonnet-20240229",
      "api_key": "${ANTHROPIC_API_KEY}",
      "timeout": 30
    }
  ],
  "use_ai_judge": true,
  "judge_model": "gpt-4",
  "sample_size": 50,
  "generate_whitepaper": true
}
```

### Configuration Options

#### Core Settings
- **name**: Benchmark identifier
- **description**: Human-readable description
- **dataset_path**: Path to normalized dataset file
- **models**: List of model configurations

#### Model Configuration
- **id**: Unique identifier for the model
- **provider**: `openai`, `anthropic`, or `local`
- **model**: Model name/version
- **api_key**: API key (supports environment variables)
- **timeout**: Request timeout in seconds
- **max_retries**: Number of retry attempts

#### Evaluation Settings
- **use_ai_judge**: Enable AI-powered evaluation
- **judge_model**: Model to use for judging (default: `gpt-4`)
- **evaluation_dimensions**: List of evaluation criteria

#### Sampling and Filtering
- **sample_size**: Number of tasks to sample (null for all)
- **random_seed**: Seed for reproducible sampling
- **filter_domains**: List of domains to include
- **filter_difficulty**: List of difficulty levels to include

#### Output Settings
- **output_dir**: Directory for results
- **save_raw_responses**: Save all model responses
- **generate_whitepaper**: Create comprehensive report

## Usage Examples

### Basic Benchmark
```bash
# Test GPT-4 and Claude on 50 random tasks
python -m aeonisk.benchmark.cli \
  --config configs/basic_benchmark.json \
  --output results/basic/
```

### Domain-Specific Testing
```json
{
  "name": "combat_benchmark",
  "filter_domains": ["combat", "skill_check_athletics"],
  "sample_size": 25
}
```

### Local Model Testing
```json
{
  "models": [
    {
      "id": "llama2",
      "provider": "local",
      "model": "llama2:7b",
      "base_url": "http://localhost:11434",
      "endpoint": "/api/generate"
    }
  ]
}
```

### Comprehensive Suite
```bash
# Run multiple benchmark configurations
python -m aeonisk.benchmark.cli \
  --config configs/base_config.json \
  --suite \
  --output results/comprehensive/
```

## Output Structure

### Generated Files
```
benchmark_results/
├── comparison_report.json          # Main comparison results
├── whitepaper.md                   # Comprehensive analysis
├── model_results/                  # Individual model results
│   ├── gpt4_results.json
│   └── claude_results.json
└── raw_responses/                  # Raw model outputs
    ├── YAGS-AEONISK-001_responses.json
    └── ...
```

### Key Metrics
- **Overall Score**: Weighted average across all dimensions
- **Success Rate**: Percentage of successfully processed tasks
- **Response Time**: Average time per response
- **Dimension Scores**: Performance in each evaluation area
- **Domain Performance**: Results by gameplay category

## API Usage

### Programmatic Access
```python
from aeonisk.benchmark import BenchmarkRunner, BenchmarkConfig

# Create configuration
config = BenchmarkConfig(
    name="custom_benchmark",
    dataset_path="datasets/sample.txt",
    models=[
        {
            "provider": "openai",
            "model": "gpt-4",
            "api_key": "your-key"
        }
    ]
)

# Run benchmark
runner = BenchmarkRunner(config)
results = await runner.run_benchmark()

# Access results
print(f"Top model: {list(results.model_rankings.keys())[0]}")
```

### Custom Evaluation
```python
from aeonisk.benchmark import AIJudge, EvaluationMetrics

# Custom AI judge
judge = AIJudge(judge_model="gpt-3.5-turbo")

# Automated metrics only
metrics = EvaluationMetrics()
accuracy = metrics.calculate_overall_accuracy(response, gold_standard)
```

## Advanced Features

### Custom Providers
Extend the system with new model providers:

```python
from aeonisk.benchmark.providers import LLMProvider

class CustomProvider(LLMProvider):
    async def generate_response(self, task):
        # Implement custom API integration
        pass
```

### Custom Evaluation Dimensions
Add new evaluation criteria:

```python
from aeonisk.benchmark.models import EvaluationDimension

# Add custom dimension to evaluation
custom_dimensions = [
    EvaluationDimension.MECHANICAL_ACCURACY,
    "custom_metric"
]
```

### Statistical Analysis
Access detailed statistics:

```python
from aeonisk.benchmark.reporter import StatisticsCollector

collector = StatisticsCollector()
task_stats = collector.calculate_task_statistics(task_id, responses, evaluations)
correlations = collector.calculate_correlation_matrix(results)
```

## Dataset Format

The system expects YAML-formatted dataset files with the following structure:

```yaml
---
task_id: YAGS-AEONISK-001
domain:
  core: rule_application
  subdomain: skill_check_athletics
scenario: >
  Character attempts a challenging athletic maneuver...
environment: Dangerous terrain with time pressure
stakes: >
  Success allows escape, failure results in injury...
characters:
  - name: Character Name
    attributes: {strength: 4, agility: 3, ...}
    skills: {athletics: 3, stealth: 2, ...}
goal: >
  Determine appropriate mechanics and outcomes...
expected_fields:
  - attribute_used
  - skill_used
  - roll_formula
  - difficulty_guess
  - outcome_explanation
gold_answer:
  attribute_used: Agility
  skill_used: Athletics
  roll_formula: "Agility 3 x Athletics 3 = 9; 9 + d20"
  difficulty_guess: 20
  outcome_explanation:
    critical_failure:
      narrative: "Catastrophic failure description..."
      mechanical_effect: "Specific game consequences..."
    # ... other outcome levels
```

## Troubleshooting

### Common Issues

#### API Key Errors
```bash
# Verify environment variables
echo $OPENAI_API_KEY
echo $ANTHROPIC_API_KEY

# Test API connectivity
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  https://api.openai.com/v1/models
```

#### Dataset Loading Issues
- Verify file path in configuration
- Check YAML formatting
- Ensure proper encoding (UTF-8)

#### Memory/Performance Issues
- Reduce `sample_size` for testing
- Lower `max_concurrent_requests`
- Disable `save_raw_responses` for large benchmarks

#### Local Model Connection
```bash
# Verify Ollama is running
curl http://localhost:11434/api/tags

# Check model availability
ollama list
```

### Debugging
```bash
# Enable verbose logging
python -m aeonisk.benchmark.cli \
  --config benchmark_config.json \
  --verbose
```

### Performance Optimization
- Use smaller sample sizes for development
- Configure appropriate timeouts
- Monitor API rate limits
- Consider local model alternatives for development

## Contributing

### Adding New Providers
1. Extend `LLMProvider` base class
2. Implement `generate_response` method
3. Add to `ProviderFactory`
4. Update configuration schema

### Improving Evaluation
1. Enhance automated metrics in `EvaluationMetrics`
2. Refine AI judge prompts
3. Add new evaluation dimensions
4. Implement domain-specific scoring

### Extending Reports
1. Add new analysis methods to `StatisticsCollector`
2. Enhance whitepaper generation
3. Create visualization outputs
4. Add export formats

## License

This project is part of the Aeonisk YAGS toolkit and follows the same licensing terms as the parent project.

## Support

For issues and questions:
1. Check this documentation
2. Review error logs with `--verbose`
3. Validate configuration files
4. Test with minimal configurations
5. Submit issues with full context and logs