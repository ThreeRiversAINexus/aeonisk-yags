"""
Command-line interface for the Aeonisk YAGS benchmarking system.

This module provides a convenient CLI for running benchmarks and generating reports.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

from .core import BenchmarkRunner, BenchmarkOrchestrator
from .models import BenchmarkConfig

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config_file(config_path: str) -> Dict[str, Any]:
    """Load configuration from a JSON file."""
    with open(config_path, 'r') as f:
        return json.load(f)


def create_sample_config(output_path: str):
    """Create a sample configuration file."""
    sample_config = {
        "name": "aeonisk_benchmark",
        "description": "Comprehensive Aeonisk YAGS model evaluation",
        "dataset_path": "datasets/aeonisk_dataset_normalized_complete.txt",
        "models": [
            {
                "id": "gpt4",
                "provider": "openai",
                "model": "gpt-4",
                "api_key": "${OPENAI_API_KEY}",
                "timeout": 30,
                "max_retries": 3
            },
            {
                "id": "gpt35",
                "provider": "openai", 
                "model": "gpt-3.5-turbo",
                "api_key": "${OPENAI_API_KEY}",
                "timeout": 30,
                "max_retries": 3
            },
            {
                "id": "claude",
                "provider": "anthropic",
                "model": "claude-3-sonnet-20240229",
                "api_key": "${ANTHROPIC_API_KEY}",
                "timeout": 30,
                "max_retries": 3
            },
            {
                "id": "local_llama",
                "provider": "local",
                "model": "llama2:7b",
                "base_url": "http://localhost:11434",
                "endpoint": "/api/generate",
                "timeout": 60,
                "max_retries": 2
            }
        ],
        "use_ai_judge": True,
        "judge_model": "gpt-4",
        "evaluation_dimensions": [
            "mechanical_accuracy",
            "narrative_quality", 
            "rules_adherence",
            "consistency",
            "creativity",
            "difficulty_appropriate",
            "overall_quality"
        ],
        "sample_size": None,
        "random_seed": 42,
        "filter_domains": None,
        "filter_difficulty": None,
        "max_concurrent_requests": 5,
        "timeout_seconds": 30,
        "retry_attempts": 3,
        "output_dir": "benchmark_results",
        "save_raw_responses": True,
        "generate_whitepaper": True,
        "version": "1.0.0"
    }
    
    with open(output_path, 'w') as f:
        json.dump(sample_config, f, indent=2)
    
    print(f"Sample configuration saved to {output_path}")
    print("Edit the configuration file to customize your benchmark settings.")


def expand_env_vars(config: Dict[str, Any]) -> Dict[str, Any]:
    """Expand environment variables in configuration values."""
    def expand_value(value):
        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            env_var = value[2:-1]
            return os.getenv(env_var, value)
        elif isinstance(value, dict):
            return {k: expand_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [expand_value(item) for item in value]
        else:
            return value
    
    return expand_value(config)


def validate_config(config: Dict[str, Any]) -> List[str]:
    """Validate configuration and return list of errors."""
    errors = []
    
    # Check required fields
    required_fields = ['name', 'dataset_path', 'models']
    for field in required_fields:
        if field not in config:
            errors.append(f"Missing required field: {field}")
    
    # Check dataset path exists
    if 'dataset_path' in config:
        dataset_path = Path(config['dataset_path'])
        if not dataset_path.exists():
            errors.append(f"Dataset file not found: {dataset_path}")
    
    # Validate models
    if 'models' in config and isinstance(config['models'], list):
        for i, model in enumerate(config['models']):
            if not isinstance(model, dict):
                errors.append(f"Model {i} is not a dictionary")
                continue
            
            # Check required model fields
            required_model_fields = ['provider', 'model']
            for field in required_model_fields:
                if field not in model:
                    errors.append(f"Model {i} missing required field: {field}")
            
            # Check API keys for cloud providers
            provider = model.get('provider')
            if provider in ['openai', 'anthropic']:
                api_key = model.get('api_key', '')
                if not api_key or (api_key.startswith('${') and api_key.endswith('}')):
                    env_var = api_key[2:-1] if api_key.startswith('${') else f"{provider.upper()}_API_KEY"
                    if not os.getenv(env_var):
                        errors.append(f"Model {i} ({provider}): Missing API key environment variable {env_var}")
    
    return errors


async def run_single_benchmark(config_path: str, output_dir: str = None) -> int:
    """Run a single benchmark from configuration file."""
    try:
        # Load and validate configuration
        config_data = load_config_file(config_path)
        config_data = expand_env_vars(config_data)
        
        # Override output directory if specified
        if output_dir:
            config_data['output_dir'] = output_dir
        
        # Validate configuration
        errors = validate_config(config_data)
        if errors:
            logger.error("Configuration validation failed:")
            for error in errors:
                logger.error(f"  - {error}")
            return 1
        
        # Create benchmark configuration
        benchmark_config = BenchmarkConfig(**config_data)
        
        # Run benchmark
        logger.info(f"Starting benchmark: {benchmark_config.name}")
        runner = BenchmarkRunner(benchmark_config)
        comparison_report = await runner.run_benchmark()
        
        logger.info(f"Benchmark completed successfully!")
        logger.info(f"Results saved to: {benchmark_config.output_dir}")
        logger.info(f"Top model: {list(comparison_report.model_rankings.keys())[0] if comparison_report.model_rankings else 'None'}")
        
        return 0
    
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        return 1


async def run_benchmark_suite(base_config_path: str, output_dir: str = None) -> int:
    """Run a suite of benchmarks with different configurations."""
    try:
        # Load base configuration
        base_config = load_config_file(base_config_path)
        base_config = expand_env_vars(base_config)
        
        # Validate base configuration
        errors = validate_config(base_config)
        if errors:
            logger.error("Base configuration validation failed:")
            for error in errors:
                logger.error(f"  - {error}")
            return 1
        
        # Create orchestrator
        orchestrator = BenchmarkOrchestrator(output_dir or "benchmark_suite_results")
        
        # Create default benchmark configurations
        configs = orchestrator.create_default_configs(
            dataset_path=base_config['dataset_path'],
            models=base_config['models']
        )
        
        # Run benchmark suite
        logger.info(f"Running benchmark suite with {len(configs)} configurations")
        results = await orchestrator.run_benchmark_suite(configs)
        
        logger.info(f"Benchmark suite completed successfully!")
        logger.info(f"Results saved to: {orchestrator.base_output_dir}")
        
        return 0
    
    except Exception as e:
        logger.error(f"Benchmark suite failed: {e}")
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Aeonisk YAGS Language Model Benchmark System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create sample configuration
  python -m aeonisk.benchmark.cli --create-config benchmark_config.json
  
  # Run single benchmark
  python -m aeonisk.benchmark.cli --config benchmark_config.json
  
  # Run benchmark suite
  python -m aeonisk.benchmark.cli --config benchmark_config.json --suite
  
  # Run with custom output directory
  python -m aeonisk.benchmark.cli --config benchmark_config.json --output results/
  
Environment Variables:
  OPENAI_API_KEY      OpenAI API key for GPT models
  ANTHROPIC_API_KEY   Anthropic API key for Claude models
        """
    )
    
    parser.add_argument(
        '--config', '-c',
        type=str,
        help='Path to benchmark configuration file'
    )
    
    parser.add_argument(
        '--create-config',
        type=str,
        metavar='OUTPUT_FILE',
        help='Create a sample configuration file'
    )
    
    parser.add_argument(
        '--suite', '-s',
        action='store_true',
        help='Run benchmark suite with multiple configurations'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        metavar='OUTPUT_DIR',
        help='Output directory for results'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--sample-config',
        action='store_true',
        help='Print sample configuration to stdout'
    )
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Handle create config
    if args.create_config:
        create_sample_config(args.create_config)
        return 0
    
    # Handle sample config
    if args.sample_config:
        create_sample_config('/tmp/sample_config.json')
        with open('/tmp/sample_config.json', 'r') as f:
            print(f.read())
        os.unlink('/tmp/sample_config.json')
        return 0
    
    # Validate arguments
    if not args.config:
        parser.error("Configuration file is required (use --config)")
    
    if not os.path.exists(args.config):
        logger.error(f"Configuration file not found: {args.config}")
        return 1
    
    # Run benchmark
    try:
        if args.suite:
            return asyncio.run(run_benchmark_suite(args.config, args.output))
        else:
            return asyncio.run(run_single_benchmark(args.config, args.output))
    
    except KeyboardInterrupt:
        logger.info("Benchmark interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())