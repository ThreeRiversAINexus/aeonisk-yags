"""
Core benchmark runner for the Aeonisk YAGS benchmarking system.

This module provides the main benchmarking functionality and orchestrates
the entire evaluation process.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from .models import (
    BenchmarkConfig, BenchmarkResult, BenchmarkTask, ModelResponse,
    EvaluationResult, ComparisonReport, EvaluationDimension
)
from .loader import DatasetLoader
from .providers import ModelManager
from .evaluator import AIJudge, ComparisonAnalyzer
from .reporter import StatisticsCollector, WhitepaperGenerator

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """Main benchmark runner for orchestrating the evaluation process."""
    
    def __init__(self, config: BenchmarkConfig):
        """Initialize the benchmark runner."""
        self.config = config
        self.dataset_loader = DatasetLoader(config.dataset_path)
        self.model_manager = ModelManager()
        self.ai_judge = AIJudge(
            judge_model=config.judge_model,
            api_key=os.getenv('OPENAI_API_KEY')
        ) if config.use_ai_judge else None
        self.stats_collector = StatisticsCollector()
        self.whitepaper_generator = WhitepaperGenerator()
        
        # Configure output directory
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize results storage
        self.results: Dict[str, BenchmarkResult] = {}
        self.task_responses: Dict[str, List[ModelResponse]] = {}
        self.evaluations: Dict[str, List[EvaluationResult]] = {}
    
    def configure_models(self):
        """Configure the LLM providers from config."""
        logger.info(f"Configuring {len(self.config.models)} models...")
        self.model_manager.configure_from_config(self.config.models)
        
        provider_info = self.model_manager.get_provider_info()
        logger.info(f"Configured providers: {list(provider_info.keys())}")
    
    def load_dataset(self) -> List[BenchmarkTask]:
        """Load and filter the dataset."""
        logger.info(f"Loading dataset from {self.config.dataset_path}...")
        
        # Load all tasks
        all_tasks = self.dataset_loader.load_dataset()
        logger.info(f"Loaded {len(all_tasks)} total tasks")
        
        # Apply filters
        filtered_tasks = self.dataset_loader.filter_tasks(
            domains=self.config.filter_domains,
            difficulty_levels=self.config.filter_difficulty,
            sample_size=self.config.sample_size,
            random_seed=self.config.random_seed
        )
        
        logger.info(f"Filtered to {len(filtered_tasks)} tasks for benchmarking")
        return filtered_tasks
    
    async def run_benchmark(self) -> ComparisonReport:
        """Run the complete benchmark process."""
        logger.info(f"Starting benchmark: {self.config.name}")
        start_time = datetime.now()
        
        try:
            # Configure models
            self.configure_models()
            
            # Load dataset
            tasks = self.load_dataset()
            
            if not tasks:
                raise ValueError("No tasks loaded for benchmarking")
            
            # Generate responses for each model
            await self.generate_all_responses(tasks)
            
            # Evaluate responses
            await self.evaluate_all_responses(tasks)
            
            # Calculate final results
            await self.calculate_results()
            
            # Generate comparison report
            comparison_report = self.generate_comparison_report(tasks, start_time)
            
            # Save results
            await self.save_results(comparison_report)
            
            # Generate whitepaper if requested
            if self.config.generate_whitepaper:
                await self.generate_whitepaper_report(comparison_report)
            
            logger.info(f"Benchmark completed in {(datetime.now() - start_time).total_seconds():.2f}s")
            return comparison_report
            
        except Exception as e:
            logger.error(f"Benchmark failed: {e}")
            raise
    
    async def generate_all_responses(self, tasks: List[BenchmarkTask]):
        """Generate responses from all models for all tasks."""
        logger.info("Generating responses from all models...")
        
        total_tasks = len(tasks)
        provider_info = self.model_manager.get_provider_info()
        
        for i, task in enumerate(tasks):
            logger.info(f"Processing task {i+1}/{total_tasks}: {task.task_id}")
            
            # Generate responses from all models for this task
            task_responses = await self.model_manager.generate_responses_parallel(task)
            
            # Store responses
            self.task_responses[task.task_id] = list(task_responses.values())
            
            # Log progress
            if (i + 1) % 10 == 0:
                logger.info(f"Completed {i+1}/{total_tasks} tasks")
    
    async def evaluate_all_responses(self, tasks: List[BenchmarkTask]):
        """Evaluate all generated responses."""
        logger.info("Evaluating all responses...")
        
        if not self.ai_judge:
            logger.warning("No AI judge configured, using automated metrics only")
            return
        
        # Prepare evaluation tasks
        evaluation_tasks = []
        for task in tasks:
            if task.task_id in self.task_responses:
                responses = self.task_responses[task.task_id]
                for response in responses:
                    evaluation_tasks.append((task, response))
        
        # Run evaluations in batches
        logger.info(f"Evaluating {len(evaluation_tasks)} responses...")
        evaluations = await self.ai_judge.evaluate_batch(evaluation_tasks)
        
        # Group evaluations by task
        for evaluation in evaluations:
            task_id = evaluation.task_id
            if task_id not in self.evaluations:
                self.evaluations[task_id] = []
            self.evaluations[task_id].append(evaluation)
    
    async def calculate_results(self):
        """Calculate final benchmark results for each model."""
        logger.info("Calculating final results...")
        
        # Group responses by model
        model_responses = {}
        for task_id, responses in self.task_responses.items():
            for response in responses:
                model_key = f"{response.provider}_{response.model_name}"
                if model_key not in model_responses:
                    model_responses[model_key] = []
                model_responses[model_key].append(response)
        
        # Calculate results for each model
        for model_key, responses in model_responses.items():
            result = await self.calculate_model_result(model_key, responses)
            self.results[model_key] = result
    
    async def calculate_model_result(self, model_key: str, responses: List[ModelResponse]) -> BenchmarkResult:
        """Calculate benchmark result for a specific model."""
        if not responses:
            return BenchmarkResult(
                model_name="unknown",
                provider="unknown",
                benchmark_config=self.config.model_dump(),
                total_tasks=0,
                completed_tasks=0,
                failed_tasks=0,
                average_response_time=0,
                overall_score=0,
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration=0
            )
        
        # Basic stats
        total_tasks = len(responses)
        completed_tasks = sum(1 for r in responses if r.successful_parse)
        failed_tasks = total_tasks - completed_tasks
        
        # Response time stats
        response_times = [r.response_time for r in responses if r.response_time > 0]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        # Token stats
        token_counts = [r.token_count for r in responses if r.token_count]
        total_tokens = sum(token_counts) if token_counts else None
        
        # Get evaluations for this model
        model_evaluations = []
        for task_id, task_evals in self.evaluations.items():
            for eval_result in task_evals:
                if eval_result.model_name == responses[0].model_name:
                    model_evaluations.append(eval_result)
        
        # Calculate scores
        if model_evaluations:
            overall_score = sum(e.overall_score for e in model_evaluations) / len(model_evaluations)
            
            # Calculate dimension scores
            dimension_scores = {}
            for dimension in EvaluationDimension:
                scores = [e.scores.get(dimension, 0) for e in model_evaluations if e.scores.get(dimension)]
                if scores:
                    dimension_scores[dimension] = sum(scores) / len(scores)
                else:
                    dimension_scores[dimension] = 0
        else:
            overall_score = 0
            dimension_scores = {dim: 0 for dim in EvaluationDimension}
        
        # Calculate domain performance
        domain_performance = self.calculate_domain_performance(responses, model_evaluations)
        
        return BenchmarkResult(
            model_name=responses[0].model_name,
            provider=responses[0].provider,
            benchmark_config=self.config.model_dump(),
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            average_response_time=avg_response_time,
            total_tokens=total_tokens,
            overall_score=overall_score,
            dimension_scores=dimension_scores,
            task_results=model_evaluations,
            domain_performance=domain_performance,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration=0
        )
    
    def calculate_domain_performance(self, responses: List[ModelResponse], evaluations: List[EvaluationResult]) -> Dict[str, Dict[str, float]]:
        """Calculate performance by domain."""
        domain_performance = {}
        
        # Group evaluations by domain (we need to match with tasks)
        for task_id, task_responses in self.task_responses.items():
            # Find the task
            task = self.dataset_loader.get_task_by_id(task_id)
            if not task:
                continue
            
            domain_key = f"{task.domain.core}.{task.domain.subdomain}"
            
            # Find evaluations for this task and model
            task_evaluations = [e for e in evaluations if e.task_id == task_id]
            
            if task_evaluations:
                if domain_key not in domain_performance:
                    domain_performance[domain_key] = {
                        'count': 0,
                        'total_score': 0,
                        'average_score': 0
                    }
                
                for eval_result in task_evaluations:
                    domain_performance[domain_key]['count'] += 1
                    domain_performance[domain_key]['total_score'] += eval_result.overall_score
                    domain_performance[domain_key]['average_score'] = (
                        domain_performance[domain_key]['total_score'] / 
                        domain_performance[domain_key]['count']
                    )
        
        return domain_performance
    
    def generate_comparison_report(self, tasks: List[BenchmarkTask], start_time: datetime) -> ComparisonReport:
        """Generate comparison report across all models."""
        logger.info("Generating comparison report...")
        
        # Model rankings
        model_rankings = {}
        sorted_models = sorted(self.results.values(), key=lambda x: x.overall_score, reverse=True)
        for i, result in enumerate(sorted_models):
            model_rankings[result.model_name] = i + 1
        
        # Dimension rankings
        dimension_rankings = {}
        for dimension in EvaluationDimension:
            dim_scores = [(r.model_name, r.dimension_scores.get(dimension, 0)) for r in self.results.values()]
            sorted_dim_scores = sorted(dim_scores, key=lambda x: x[1], reverse=True)
            dimension_rankings[dimension] = {name: i + 1 for i, (name, _) in enumerate(sorted_dim_scores)}
        
        # Domain comparisons
        domain_comparisons = self.calculate_domain_comparisons()
        
        # Statistical analysis
        statistical_significance = self.calculate_statistical_significance()
        effect_sizes = self.calculate_effect_sizes()
        
        return ComparisonReport(
            benchmark_name=self.config.name,
            models=list(model_rankings.keys()),
            dataset_version=self.config.version,
            total_tasks=len(tasks),
            model_rankings=model_rankings,
            dimension_rankings=dimension_rankings,
            statistical_significance=statistical_significance,
            effect_sizes=effect_sizes,
            domain_comparisons=domain_comparisons,
            results=list(self.results.values()),
            analysis_notes=f"Benchmark completed with {len(tasks)} tasks across {len(self.results)} models"
        )
    
    def calculate_domain_comparisons(self) -> Dict[str, Dict[str, float]]:
        """Calculate domain-specific comparisons."""
        domain_comparisons = {}
        
        # Get all unique domains
        all_domains = set()
        for result in self.results.values():
            all_domains.update(result.domain_performance.keys())
        
        # Calculate comparisons for each domain
        for domain in all_domains:
            domain_scores = {}
            for model_name, result in self.results.items():
                if domain in result.domain_performance:
                    domain_scores[model_name] = result.domain_performance[domain].get('average_score', 0)
            
            if domain_scores:
                domain_comparisons[domain] = domain_scores
        
        return domain_comparisons
    
    def calculate_statistical_significance(self) -> Dict[str, Dict[str, float]]:
        """Calculate statistical significance between models."""
        # This would use statistical tests like t-tests
        # For now, return placeholder
        return {}
    
    def calculate_effect_sizes(self) -> Dict[str, Dict[str, float]]:
        """Calculate effect sizes between models."""
        # This would calculate Cohen's d or similar
        # For now, return placeholder
        return {}
    
    async def save_results(self, comparison_report: ComparisonReport):
        """Save benchmark results to files."""
        logger.info(f"Saving results to {self.output_dir}")
        
        # Save main comparison report
        report_file = self.output_dir / "comparison_report.json"
        with open(report_file, 'w') as f:
            json.dump(comparison_report.model_dump(), f, indent=2, default=str)
        
        # Save individual model results
        results_dir = self.output_dir / "model_results"
        results_dir.mkdir(exist_ok=True)
        
        for model_name, result in self.results.items():
            model_file = results_dir / f"{model_name.replace('/', '_')}_results.json"
            with open(model_file, 'w') as f:
                json.dump(result.model_dump(), f, indent=2, default=str)
        
        # Save raw responses if requested
        if self.config.save_raw_responses:
            responses_dir = self.output_dir / "raw_responses"
            responses_dir.mkdir(exist_ok=True)
            
            for task_id, responses in self.task_responses.items():
                task_file = responses_dir / f"{task_id}_responses.json"
                responses_data = [r.model_dump() for r in responses]
                with open(task_file, 'w') as f:
                    json.dump(responses_data, f, indent=2, default=str)
        
        logger.info(f"Results saved to {self.output_dir}")
    
    async def generate_whitepaper_report(self, comparison_report: ComparisonReport):
        """Generate whitepaper-style report."""
        logger.info("Generating whitepaper report...")
        
        whitepaper_content = self.whitepaper_generator.generate_whitepaper(
            comparison_report,
            self.config,
            self.task_responses,
            self.evaluations
        )
        
        whitepaper_file = self.output_dir / "whitepaper.md"
        with open(whitepaper_file, 'w') as f:
            f.write(whitepaper_content)
        
        logger.info(f"Whitepaper saved to {whitepaper_file}")


class BenchmarkOrchestrator:
    """High-level orchestrator for running multiple benchmarks."""
    
    def __init__(self, base_output_dir: str = "benchmark_results"):
        self.base_output_dir = Path(base_output_dir)
        self.base_output_dir.mkdir(parents=True, exist_ok=True)
    
    async def run_benchmark_suite(self, configs: List[BenchmarkConfig]) -> List[ComparisonReport]:
        """Run a suite of benchmarks with different configurations."""
        logger.info(f"Running benchmark suite with {len(configs)} configurations")
        
        results = []
        for i, config in enumerate(configs):
            logger.info(f"Running benchmark {i+1}/{len(configs)}: {config.name}")
            
            # Create output directory for this benchmark
            benchmark_dir = self.base_output_dir / f"benchmark_{i+1}_{config.name}"
            config.output_dir = str(benchmark_dir)
            
            # Run benchmark
            runner = BenchmarkRunner(config)
            result = await runner.run_benchmark()
            results.append(result)
            
            logger.info(f"Completed benchmark {i+1}/{len(configs)}")
        
        # Generate meta-analysis
        await self.generate_meta_analysis(results)
        
        return results
    
    async def generate_meta_analysis(self, results: List[ComparisonReport]):
        """Generate meta-analysis across multiple benchmarks."""
        logger.info("Generating meta-analysis...")
        
        # This would analyze trends across different benchmark configurations
        # For now, just create a summary
        meta_analysis = {
            'total_benchmarks': len(results),
            'total_models': len(set(model for result in results for model in result.models)),
            'benchmark_summaries': [
                {
                    'name': result.benchmark_name,
                    'top_model': list(result.model_rankings.keys())[0] if result.model_rankings else 'None',
                    'total_tasks': result.total_tasks
                }
                for result in results
            ]
        }
        
        meta_file = self.base_output_dir / "meta_analysis.json"
        with open(meta_file, 'w') as f:
            json.dump(meta_analysis, f, indent=2, default=str)
        
        logger.info(f"Meta-analysis saved to {meta_file}")
    
    def create_default_configs(self, dataset_path: str, models: List[Dict[str, Any]]) -> List[BenchmarkConfig]:
        """Create default benchmark configurations."""
        configs = []
        
        # Full benchmark
        configs.append(BenchmarkConfig(
            name="full_benchmark",
            description="Complete benchmark across all tasks",
            dataset_path=dataset_path,
            models=models,
            sample_size=None,
            random_seed=42
        ))
        
        # Sample benchmark
        configs.append(BenchmarkConfig(
            name="sample_benchmark",
            description="Sample benchmark for quick evaluation",
            dataset_path=dataset_path,
            models=models,
            sample_size=50,
            random_seed=42
        ))
        
        # Domain-specific benchmarks
        for domain in ["rule_application", "ritual_check", "combat"]:
            configs.append(BenchmarkConfig(
                name=f"{domain}_benchmark",
                description=f"Benchmark focused on {domain} tasks",
                dataset_path=dataset_path,
                models=models,
                filter_domains=[domain],
                sample_size=None,
                random_seed=42
            ))
        
        return configs