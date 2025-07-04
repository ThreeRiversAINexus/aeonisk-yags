"""
Comprehensive test suite for the Aeonisk YAGS benchmark system.

This test suite covers all major components of the benchmarking system,
including CLI commands, model evaluation, and report generation.
All external API calls are mocked to prevent real costs.
"""

import pytest
import asyncio
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from typing import Dict, Any, List

# Import benchmark modules
from aeonisk.benchmark import (
    BenchmarkRunner, BenchmarkConfig, BenchmarkResult,
    BenchmarkOrchestrator, AIJudge, EvaluationMetrics
)
from aeonisk.benchmark.cli import (
    main, create_sample_config, validate_config, 
    run_single_benchmark, run_benchmark_suite
)
from aeonisk.benchmark.core import BenchmarkRunner
from aeonisk.benchmark.models import (
    BenchmarkTask, ModelResponse, EvaluationResult,
    ComparisonReport, EvaluationDimension
)
from aeonisk.benchmark.loader import DatasetLoader
from aeonisk.benchmark.providers import ModelManager
from aeonisk.benchmark.evaluator import AIJudge
from aeonisk.benchmark.reporter import WhitepaperGenerator


class TestBenchmarkConfig:
    """Test suite for BenchmarkConfig validation and creation."""
    
    def test_config_creation_with_defaults(self):
        """Test creating a config with default values."""
        config = BenchmarkConfig(
            name="test_benchmark",
            description="Test benchmark",
            dataset_path="test_dataset.txt",
            models=[{
                "id": "test_model",
                "provider": "openai",
                "model": "gpt-4"
            }]
        )
        
        assert config.name == "test_benchmark"
        assert config.use_ai_judge is True
        assert config.judge_model == "gpt-4"
        assert config.sample_size is None
        assert config.timeout_seconds == 30
        assert config.max_concurrent_requests == 5
        assert config.output_dir == "benchmark_results"
        assert config.save_raw_responses is True
        assert config.generate_whitepaper is True
    
    def test_config_with_custom_values(self):
        """Test creating a config with custom values."""
        config = BenchmarkConfig(
            name="custom_benchmark",
            description="Custom test benchmark",
            dataset_path="custom_dataset.txt",
            models=[{
                "id": "custom_model",
                "provider": "anthropic",
                "model": "claude-3-sonnet-20240229"
            }],
            use_ai_judge=False,
            judge_model="gpt-3.5-turbo",
            sample_size=25,
            timeout_seconds=60,
            max_concurrent_requests=10,
            output_dir="custom_results",
            save_raw_responses=False,
            generate_whitepaper=False
        )
        
        assert config.name == "custom_benchmark"
        assert config.use_ai_judge is False
        assert config.judge_model == "gpt-3.5-turbo"
        assert config.sample_size == 25
        assert config.timeout_seconds == 60
        assert config.max_concurrent_requests == 10
        assert config.output_dir == "custom_results"
        assert config.save_raw_responses is False
        assert config.generate_whitepaper is False


class TestBenchmarkCLI:
    """Test suite for the benchmark CLI functionality."""
    
    def test_create_sample_config(self):
        """Test creating a sample configuration file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_path = f.name
        
        try:
            create_sample_config(config_path)
            
            # Verify the file was created
            assert os.path.exists(config_path)
            
            # Verify the content is valid JSON
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            assert 'name' in config_data
            assert 'dataset_path' in config_data
            assert 'models' in config_data
            assert isinstance(config_data['models'], list)
            assert len(config_data['models']) > 0
            
        finally:
            if os.path.exists(config_path):
                os.unlink(config_path)
    
    def test_validate_config_valid(self):
        """Test validating a valid configuration."""
        config = {
            "name": "test_benchmark",
            "dataset_path": __file__,  # Use this file as a fake dataset
            "models": [
                {
                    "provider": "openai",
                    "model": "gpt-4",
                    "api_key": "test_key"
                }
            ]
        }
        
        errors = validate_config(config)
        assert len(errors) == 0
    
    def test_validate_config_missing_fields(self):
        """Test validating a config with missing required fields."""
        config = {
            "name": "test_benchmark"
            # Missing dataset_path and models
        }
        
        errors = validate_config(config)
        assert len(errors) >= 2  # Should have at least 2 errors
        assert any("dataset_path" in error for error in errors)
        assert any("models" in error for error in errors)
    
    def test_validate_config_missing_dataset(self):
        """Test validating a config with non-existent dataset."""
        config = {
            "name": "test_benchmark",
            "dataset_path": "/nonexistent/path/to/dataset.txt",
            "models": [
                {
                    "provider": "openai",
                    "model": "gpt-4",
                    "api_key": "test_key"
                }
            ]
        }
        
        errors = validate_config(config)
        assert len(errors) >= 1
        assert any("Dataset file not found" in error for error in errors)
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test_key'})
    @patch('aeonisk.benchmark.cli.BenchmarkRunner')
    @patch('aeonisk.benchmark.cli.load_config_file')
    async def test_run_single_benchmark_success(self, mock_load_config, mock_runner_class):
        """Test running a single benchmark successfully."""
        # Mock configuration
        mock_config = {
            "name": "test_benchmark",
            "dataset_path": __file__,
            "models": [
                {
                    "provider": "openai",
                    "model": "gpt-4",
                    "api_key": "${OPENAI_API_KEY}"
                }
            ]
        }
        mock_load_config.return_value = mock_config
        
        # Mock runner
        mock_runner = Mock()
        mock_comparison_report = Mock()
        mock_comparison_report.model_rankings = {"gpt-4": 1}
        mock_runner.run_benchmark = AsyncMock(return_value=mock_comparison_report)
        mock_runner_class.return_value = mock_runner
        
        # Run benchmark
        result = await run_single_benchmark("fake_config.json")
        
        assert result == 0
        mock_runner.run_benchmark.assert_called_once()
        mock_runner_class.assert_called_once()
    
    @patch('aeonisk.benchmark.cli.BenchmarkOrchestrator')
    @patch('aeonisk.benchmark.cli.load_config_file')
    async def test_run_benchmark_suite_success(self, mock_load_config, mock_orchestrator_class):
        """Test running a benchmark suite successfully."""
        # Mock configuration
        mock_config = {
            "name": "test_benchmark",
            "dataset_path": __file__,
            "models": [
                {
                    "provider": "openai",
                    "model": "gpt-4",
                    "api_key": "test_key"
                }
            ]
        }
        mock_load_config.return_value = mock_config
        
        # Mock orchestrator
        mock_orchestrator = Mock()
        mock_orchestrator.base_output_dir = "test_results"
        mock_orchestrator.create_default_configs.return_value = [Mock()]
        mock_orchestrator.run_benchmark_suite = AsyncMock(return_value=[Mock()])
        mock_orchestrator_class.return_value = mock_orchestrator
        
        # Run benchmark suite
        result = await run_benchmark_suite("fake_config.json")
        
        assert result == 0
        mock_orchestrator.run_benchmark_suite.assert_called_once()
        mock_orchestrator_class.assert_called_once()


class TestBenchmarkRunner:
    """Test suite for the BenchmarkRunner class."""
    
    @pytest.fixture
    def sample_config(self):
        """Create a sample benchmark configuration."""
        return BenchmarkConfig(
            name="test_benchmark",
            description="Test benchmark",
            dataset_path="test_dataset.txt",
            models=[{
                "id": "test_model",
                "provider": "openai",
                "model": "gpt-4",
                "api_key": "test_key"
            }],
            sample_size=5,
            generate_whitepaper=False
        )
    
    @pytest.fixture
    def sample_tasks(self):
        """Create sample benchmark tasks."""
        return [
            BenchmarkTask(
                task_id="YAGS-TEST-001",
                domain={"core": "rule_application", "subdomain": "skill_check"},
                scenario="Test scenario 1",
                environment="Test environment",
                stakes="Test stakes",
                characters=[{"name": "Test Character"}],
                goal="Test goal",
                expected_fields=["test_field"],
                gold_answer={"test_field": "test_value"}
            ),
            BenchmarkTask(
                task_id="YAGS-TEST-002",
                domain={"core": "combat", "subdomain": "melee"},
                scenario="Test scenario 2",
                environment="Test environment",
                stakes="Test stakes",
                characters=[{"name": "Test Character"}],
                goal="Test goal",
                expected_fields=["test_field"],
                gold_answer={"test_field": "test_value"}
            )
        ]
    
    @patch('aeonisk.benchmark.core.DatasetLoader')
    @patch('aeonisk.benchmark.core.ModelManager')
    @patch('aeonisk.benchmark.core.AIJudge')
    def test_benchmark_runner_initialization(self, mock_ai_judge, mock_model_manager, mock_dataset_loader, sample_config):
        """Test BenchmarkRunner initialization."""
        runner = BenchmarkRunner(sample_config)
        
        assert runner.config == sample_config
        assert runner.output_dir == Path(sample_config.output_dir)
        assert runner.results == {}
        assert runner.task_responses == {}
        assert runner.evaluations == {}
        
        # Verify components were initialized
        mock_dataset_loader.assert_called_once_with(sample_config.dataset_path)
        mock_model_manager.assert_called_once()
        mock_ai_judge.assert_called_once()
    
    @patch('aeonisk.benchmark.core.DatasetLoader')
    @patch('aeonisk.benchmark.core.ModelManager')
    @patch('aeonisk.benchmark.core.AIJudge')
    def test_configure_models(self, mock_ai_judge, mock_model_manager, mock_dataset_loader, sample_config):
        """Test model configuration."""
        runner = BenchmarkRunner(sample_config)
        
        # Mock model manager
        mock_manager = Mock()
        mock_manager.get_provider_info.return_value = {"openai": {"models": ["gpt-4"]}}
        runner.model_manager = mock_manager
        
        runner.configure_models()
        
        mock_manager.configure_from_config.assert_called_once_with(sample_config.models)
        mock_manager.get_provider_info.assert_called_once()
    
    @patch('aeonisk.benchmark.core.DatasetLoader')
    @patch('aeonisk.benchmark.core.ModelManager')
    @patch('aeonisk.benchmark.core.AIJudge')
    def test_load_dataset(self, mock_ai_judge, mock_model_manager, mock_dataset_loader, sample_config, sample_tasks):
        """Test dataset loading and filtering."""
        runner = BenchmarkRunner(sample_config)
        
        # Mock dataset loader
        mock_loader = Mock()
        mock_loader.load_dataset.return_value = sample_tasks
        mock_loader.filter_tasks.return_value = sample_tasks[:1]  # Return only first task
        runner.dataset_loader = mock_loader
        
        tasks = runner.load_dataset()
        
        assert len(tasks) == 1
        assert tasks[0].task_id == "YAGS-TEST-001"
        
        mock_loader.load_dataset.assert_called_once()
        mock_loader.filter_tasks.assert_called_once()
    
    @patch('aeonisk.benchmark.core.DatasetLoader')
    @patch('aeonisk.benchmark.core.ModelManager')
    @patch('aeonisk.benchmark.core.AIJudge')
    async def test_generate_all_responses(self, mock_ai_judge, mock_model_manager, mock_dataset_loader, sample_config, sample_tasks):
        """Test generating responses from all models."""
        runner = BenchmarkRunner(sample_config)
        
        # Mock model manager
        mock_manager = Mock()
        mock_response = ModelResponse(
            task_id="YAGS-TEST-001",
            model_name="gpt-4",
            provider="openai",
            raw_response="Test response",
            successful_parse=True,
            response_time=1.0
        )
        mock_manager.generate_responses_parallel = AsyncMock(return_value={"gpt-4": mock_response})
        mock_manager.get_provider_info.return_value = {"openai": {"models": ["gpt-4"]}}
        runner.model_manager = mock_manager
        
        await runner.generate_all_responses([sample_tasks[0]])
        
        assert "YAGS-TEST-001" in runner.task_responses
        assert len(runner.task_responses["YAGS-TEST-001"]) == 1
        
        mock_manager.generate_responses_parallel.assert_called_once()
    
    @patch('aeonisk.benchmark.core.DatasetLoader')
    @patch('aeonisk.benchmark.core.ModelManager')
    @patch('aeonisk.benchmark.core.AIJudge')
    async def test_evaluate_all_responses(self, mock_ai_judge_class, mock_model_manager, mock_dataset_loader, sample_config, sample_tasks):
        """Test evaluating all responses with AI judge."""
        runner = BenchmarkRunner(sample_config)
        
        # Mock AI judge
        mock_judge = Mock()
        mock_evaluation = EvaluationResult(
            task_id="YAGS-TEST-001",
            model_name="gpt-4",
            overall_score=0.8,
            scores={EvaluationDimension.MECHANICAL_ACCURACY: 0.9}
        )
        mock_judge.evaluate_batch = AsyncMock(return_value=[mock_evaluation])
        runner.ai_judge = mock_judge
        
        # Set up task responses
        mock_response = ModelResponse(
            task_id="YAGS-TEST-001",
            model_name="gpt-4",
            provider="openai",
            raw_response="Test response",
            successful_parse=True,
            response_time=1.0
        )
        runner.task_responses = {"YAGS-TEST-001": [mock_response]}
        
        await runner.evaluate_all_responses([sample_tasks[0]])
        
        assert "YAGS-TEST-001" in runner.evaluations
        assert len(runner.evaluations["YAGS-TEST-001"]) == 1
        
        mock_judge.evaluate_batch.assert_called_once()


class TestModelManager:
    """Test suite for the ModelManager class."""
    
    @patch('aeonisk.benchmark.providers.OpenAIProvider')
    @patch('aeonisk.benchmark.providers.AnthropicProvider')
    def test_configure_from_config(self, mock_anthropic, mock_openai):
        """Test configuring model manager from configuration."""
        from aeonisk.benchmark.providers import ModelManager
        
        manager = ModelManager()
        models_config = [
            {
                "id": "gpt4",
                "provider": "openai",
                "model": "gpt-4",
                "api_key": "test_key"
            },
            {
                "id": "claude",
                "provider": "anthropic",
                "model": "claude-3-sonnet-20240229",
                "api_key": "test_key"
            }
        ]
        
        manager.configure_from_config(models_config)
        
        # Verify providers were configured
        mock_openai.assert_called_once()
        mock_anthropic.assert_called_once()
    
    @patch('aeonisk.benchmark.providers.OpenAIProvider')
    async def test_generate_responses_parallel(self, mock_openai):
        """Test generating responses in parallel."""
        from aeonisk.benchmark.providers import ModelManager
        
        manager = ModelManager()
        
        # Mock provider
        mock_provider = Mock()
        mock_response = ModelResponse(
            task_id="YAGS-TEST-001",
            model_name="gpt-4",
            provider="openai",
            raw_response="Test response",
            successful_parse=True,
            response_time=1.0
        )
        mock_provider.generate_response = AsyncMock(return_value=mock_response)
        manager.providers = {"gpt-4": mock_provider}
        
        # Create sample task
        task = BenchmarkTask(
            task_id="YAGS-TEST-001",
            domain={"core": "rule_application", "subdomain": "skill_check"},
            scenario="Test scenario",
            environment="Test environment",
            stakes="Test stakes",
            characters=[{"name": "Test Character"}],
            goal="Test goal",
            expected_fields=["test_field"],
            gold_answer={"test_field": "test_value"}
        )
        
        responses = await manager.generate_responses_parallel(task)
        
        assert "gpt-4" in responses
        assert responses["gpt-4"].task_id == "YAGS-TEST-001"
        
        mock_provider.generate_response.assert_called_once_with(task)


class TestAIJudge:
    """Test suite for the AI Judge evaluation system."""
    
    @patch('aeonisk.benchmark.evaluator.openai.chat.completions.create')
    def test_ai_judge_initialization(self, mock_openai):
        """Test AI judge initialization."""
        judge = AIJudge(judge_model="gpt-4", api_key="test_key")
        
        assert judge.judge_model == "gpt-4"
        assert judge.api_key == "test_key"
    
    @patch('aeonisk.benchmark.evaluator.openai.chat.completions.create')
    async def test_evaluate_single_response(self, mock_openai):
        """Test evaluating a single response."""
        # Mock OpenAI response
        mock_openai.return_value.choices = [Mock()]
        mock_openai.return_value.choices[0].message.content = json.dumps({
            "mechanical_accuracy": 0.8,
            "narrative_quality": 0.9,
            "rules_adherence": 0.7,
            "consistency": 0.8,
            "creativity": 0.6,
            "difficulty_appropriate": 0.8,
            "overall_quality": 0.8,
            "reasoning": "Test reasoning"
        })
        
        judge = AIJudge(judge_model="gpt-4", api_key="test_key")
        
        task = BenchmarkTask(
            task_id="YAGS-TEST-001",
            domain={"core": "rule_application", "subdomain": "skill_check"},
            scenario="Test scenario",
            environment="Test environment",
            stakes="Test stakes",
            characters=[{"name": "Test Character"}],
            goal="Test goal",
            expected_fields=["test_field"],
            gold_answer={"test_field": "test_value"}
        )
        
        response = ModelResponse(
            task_id="YAGS-TEST-001",
            model_name="gpt-4",
            provider="openai",
            raw_response="Test response",
            successful_parse=True,
            response_time=1.0
        )
        
        evaluation = await judge.evaluate_single_response(task, response)
        
        assert evaluation.task_id == "YAGS-TEST-001"
        assert evaluation.model_name == "gpt-4"
        assert evaluation.overall_score == 0.8
        assert EvaluationDimension.MECHANICAL_ACCURACY in evaluation.scores
        
        mock_openai.assert_called_once()
    
    @patch('aeonisk.benchmark.evaluator.openai.chat.completions.create')
    async def test_evaluate_batch(self, mock_openai):
        """Test evaluating a batch of responses."""
        # Mock OpenAI response
        mock_openai.return_value.choices = [Mock()]
        mock_openai.return_value.choices[0].message.content = json.dumps({
            "mechanical_accuracy": 0.8,
            "narrative_quality": 0.9,
            "rules_adherence": 0.7,
            "consistency": 0.8,
            "creativity": 0.6,
            "difficulty_appropriate": 0.8,
            "overall_quality": 0.8,
            "reasoning": "Test reasoning"
        })
        
        judge = AIJudge(judge_model="gpt-4", api_key="test_key")
        
        task = BenchmarkTask(
            task_id="YAGS-TEST-001",
            domain={"core": "rule_application", "subdomain": "skill_check"},
            scenario="Test scenario",
            environment="Test environment",
            stakes="Test stakes",
            characters=[{"name": "Test Character"}],
            goal="Test goal",
            expected_fields=["test_field"],
            gold_answer={"test_field": "test_value"}
        )
        
        response = ModelResponse(
            task_id="YAGS-TEST-001",
            model_name="gpt-4",
            provider="openai",
            raw_response="Test response",
            successful_parse=True,
            response_time=1.0
        )
        
        evaluations = await judge.evaluate_batch([(task, response)])
        
        assert len(evaluations) == 1
        assert evaluations[0].task_id == "YAGS-TEST-001"
        assert evaluations[0].model_name == "gpt-4"
        
        mock_openai.assert_called_once()


class TestDatasetLoader:
    """Test suite for the DatasetLoader class."""
    
    def test_dataset_loader_initialization(self):
        """Test dataset loader initialization."""
        loader = DatasetLoader("test_dataset.txt")
        
        assert loader.dataset_path == "test_dataset.txt"
    
    def test_filter_tasks(self):
        """Test filtering tasks by domain and difficulty."""
        loader = DatasetLoader("test_dataset.txt")
        
        tasks = [
            BenchmarkTask(
                task_id="YAGS-TEST-001",
                domain={"core": "rule_application", "subdomain": "skill_check"},
                scenario="Test scenario 1",
                environment="Test environment",
                stakes="Test stakes",
                characters=[{"name": "Test Character"}],
                goal="Test goal",
                expected_fields=["test_field"],
                gold_answer={"test_field": "test_value"}
            ),
            BenchmarkTask(
                task_id="YAGS-TEST-002",
                domain={"core": "combat", "subdomain": "melee"},
                scenario="Test scenario 2",
                environment="Test environment",
                stakes="Test stakes",
                characters=[{"name": "Test Character"}],
                goal="Test goal",
                expected_fields=["test_field"],
                gold_answer={"test_field": "test_value"}
            ),
            BenchmarkTask(
                task_id="YAGS-TEST-003",
                domain={"core": "rule_application", "subdomain": "ritual"},
                scenario="Test scenario 3",
                environment="Test environment",
                stakes="Test stakes",
                characters=[{"name": "Test Character"}],
                goal="Test goal",
                expected_fields=["test_field"],
                gold_answer={"test_field": "test_value"}
            )
        ]
        
        # Test filtering by domain
        filtered = loader.filter_tasks(
            tasks=tasks,
            domains=["rule_application"],
            sample_size=None,
            random_seed=42
        )
        
        assert len(filtered) == 2
        assert all(task.domain["core"] == "rule_application" for task in filtered)
        
        # Test filtering by sample size
        filtered = loader.filter_tasks(
            tasks=tasks,
            domains=None,
            sample_size=2,
            random_seed=42
        )
        
        assert len(filtered) == 2
        
        # Test filtering by both domain and sample size
        filtered = loader.filter_tasks(
            tasks=tasks,
            domains=["rule_application"],
            sample_size=1,
            random_seed=42
        )
        
        assert len(filtered) == 1
        assert filtered[0].domain["core"] == "rule_application"


class TestWhitepaperGenerator:
    """Test suite for the WhitepaperGenerator class."""
    
    def test_whitepaper_generator_initialization(self):
        """Test whitepaper generator initialization."""
        generator = WhitepaperGenerator()
        
        assert generator is not None
    
    def test_generate_whitepaper(self):
        """Test generating a whitepaper report."""
        generator = WhitepaperGenerator()
        
        # Create sample comparison report
        comparison_report = ComparisonReport(
            benchmark_name="Test Benchmark",
            models=["gpt-4", "claude-3-sonnet"],
            dataset_version="1.0.0",
            total_tasks=10,
            model_rankings={"gpt-4": 1, "claude-3-sonnet": 2},
            dimension_rankings={
                EvaluationDimension.MECHANICAL_ACCURACY: {"gpt-4": 1, "claude-3-sonnet": 2}
            },
            statistical_significance={},
            effect_sizes={},
            domain_comparisons={},
            results=[],
            analysis_notes="Test analysis"
        )
        
        whitepaper = generator.generate_whitepaper(comparison_report)
        
        assert isinstance(whitepaper, str)
        assert "Test Benchmark" in whitepaper
        assert "gpt-4" in whitepaper
        assert "claude-3-sonnet" in whitepaper


if __name__ == "__main__":
    pytest.main([__file__, "-v"])