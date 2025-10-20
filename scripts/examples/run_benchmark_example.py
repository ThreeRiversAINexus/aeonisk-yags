#!/usr/bin/env python3
"""
Example script for running the Aeonisk YAGS benchmark system.

This script demonstrates how to use the benchmarking framework programmatically
to evaluate language models on Aeonisk YAGS gameplay tasks.
"""

import asyncio
import logging
import os
from pathlib import Path

from aeonisk.benchmark import (
    BenchmarkRunner, BenchmarkOrchestrator, BenchmarkConfig,
    DatasetLoader, StatisticsCollector
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_simple_benchmark():
    """Run a simple benchmark with GPT-4 and Claude."""
    print("=== Running Simple Benchmark ===")
    
    # Define the models to test
    models = [
        {
            "id": "gpt4",
            "provider": "openai",
            "model": "gpt-4",
            "api_key": os.getenv('OPENAI_API_KEY'),
            "timeout": 30
        },
        {
            "id": "claude_sonnet",
            "provider": "anthropic", 
            "model": "claude-3-sonnet-20240229",
            "api_key": os.getenv('ANTHROPIC_API_KEY'),
            "timeout": 30
        }
    ]
    
    # Create benchmark configuration
    config = BenchmarkConfig(
        name="simple_benchmark",
        description="Quick evaluation of GPT-4 vs Claude on Aeonisk tasks",
        dataset_path="datasets/aeonisk_dataset_normalized_complete.txt",
        models=models,
        sample_size=10,  # Small sample for quick test
        random_seed=42,
        use_ai_judge=True,
        judge_model="gpt-4",
        output_dir="example_results/simple",
        generate_whitepaper=True
    )
    
    # Run the benchmark
    runner = BenchmarkRunner(config)
    try:
        results = await runner.run_benchmark()
        
        # Print summary
        print("\n=== Benchmark Results ===")
        print(f"Total tasks: {results.total_tasks}")
        print(f"Models evaluated: {len(results.models)}")
        
        if results.model_rankings:
            top_model = list(results.model_rankings.keys())[0]
            print(f"Top performing model: {top_model}")
        
        print(f"Results saved to: {config.output_dir}")
        
        return results
    
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        return None


async def run_domain_specific_benchmark():
    """Run benchmarks focused on specific domains."""
    print("\n=== Running Domain-Specific Benchmarks ===")
    
    # Test different domains separately
    domains_to_test = [
        ("athletics", ["skill_check_athletics"]),
        ("rituals", ["ritual_check_binding_breath", "ritual_check"]),
        ("combat", ["combat", "skill_check_melee"])
    ]
    
    models = [
        {
            "id": "gpt4",
            "provider": "openai",
            "model": "gpt-4",
            "api_key": os.getenv('OPENAI_API_KEY')
        }
    ]
    
    all_results = {}
    
    for domain_name, domain_filters in domains_to_test:
        print(f"\nTesting domain: {domain_name}")
        
        config = BenchmarkConfig(
            name=f"{domain_name}_benchmark",
            description=f"Evaluation focused on {domain_name} tasks",
            dataset_path="datasets/aeonisk_dataset_normalized_complete.txt",
            models=models,
            filter_domains=domain_filters,
            sample_size=5,  # Very small for example
            output_dir=f"example_results/{domain_name}",
            use_ai_judge=False,  # Faster without AI judge
            generate_whitepaper=False
        )
        
        runner = BenchmarkRunner(config)
        try:
            results = await runner.run_benchmark()
            all_results[domain_name] = results
            
            if results.results:
                score = results.results[0].overall_score
                print(f"  Score: {score:.2f}")
        
        except Exception as e:
            logger.error(f"Domain benchmark {domain_name} failed: {e}")
    
    return all_results


async def run_comprehensive_suite():
    """Run a comprehensive benchmark suite."""
    print("\n=== Running Comprehensive Suite ===")
    
    # Base configuration
    base_models = [
        {
            "id": "gpt35",
            "provider": "openai",
            "model": "gpt-3.5-turbo",
            "api_key": os.getenv('OPENAI_API_KEY')
        },
        {
            "id": "claude_haiku",
            "provider": "anthropic",
            "model": "claude-3-haiku-20240307", 
            "api_key": os.getenv('ANTHROPIC_API_KEY')
        }
    ]
    
    # Create orchestrator
    orchestrator = BenchmarkOrchestrator("example_results/comprehensive")
    
    # Create custom configurations
    configs = [
        BenchmarkConfig(
            name="quick_sample",
            description="Quick sample benchmark",
            dataset_path="datasets/aeonisk_dataset_normalized_complete.txt",
            models=base_models,
            sample_size=15,
            random_seed=42,
            use_ai_judge=False
        ),
        BenchmarkConfig(
            name="athletics_focus",
            description="Athletics-focused benchmark",
            dataset_path="datasets/aeonisk_dataset_normalized_complete.txt",
            models=base_models,
            filter_domains=["skill_check_athletics"],
            sample_size=10,
            random_seed=42,
            use_ai_judge=False
        )
    ]
    
    try:
        results = await orchestrator.run_benchmark_suite(configs)
        
        print(f"\nCompleted {len(results)} benchmark configurations")
        print(f"Results saved to: {orchestrator.base_output_dir}")
        
        return results
    
    except Exception as e:
        logger.error(f"Comprehensive suite failed: {e}")
        return []


def analyze_dataset():
    """Analyze the dataset structure and statistics."""
    print("\n=== Dataset Analysis ===")
    
    try:
        # Load dataset
        loader = DatasetLoader("datasets/aeonisk_dataset_normalized_complete.txt")
        tasks = loader.load_dataset()
        
        # Get statistics
        stats = loader.get_task_statistics()
        
        print(f"Total tasks: {stats.get('total_tasks', 0)}")
        print(f"Domains: {len(stats.get('domains', {}))}")
        print(f"Difficulty levels: {len(stats.get('difficulty_levels', {}))}")
        
        # Show domain distribution
        if 'domains' in stats:
            print("\nDomain distribution:")
            for domain, count in sorted(stats['domains'].items()):
                print(f"  {domain}: {count} tasks")
        
        # Show difficulty distribution
        if 'difficulty_levels' in stats:
            print("\nDifficulty distribution:")
            for level, count in sorted(stats['difficulty_levels'].items()):
                print(f"  {level}: {count} tasks")
        
        return stats
    
    except Exception as e:
        logger.error(f"Dataset analysis failed: {e}")
        return None


async def main():
    """Main example function."""
    print("Aeonisk YAGS Benchmark System - Example Usage")
    print("=" * 50)
    
    # Check API keys
    if not os.getenv('OPENAI_API_KEY'):
        print("Warning: OPENAI_API_KEY not set")
    if not os.getenv('ANTHROPIC_API_KEY'):
        print("Warning: ANTHROPIC_API_KEY not set")
    
    # Analyze dataset first
    analyze_dataset()
    
    # Run different types of benchmarks
    try:
        # Simple benchmark
        await run_simple_benchmark()
        
        # Domain-specific benchmarks
        await run_domain_specific_benchmark()
        
        # Comprehensive suite
        await run_comprehensive_suite()
        
        print("\n=== All Examples Completed ===")
        print("Check the example_results/ directory for outputs")
    
    except Exception as e:
        logger.error(f"Example execution failed: {e}")


if __name__ == "__main__":
    # Run the example
    asyncio.run(main())