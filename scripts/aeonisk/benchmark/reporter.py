"""
Reporting and whitepaper generation for the Aeonisk YAGS benchmarking system.

This module provides comprehensive reporting capabilities including statistical
analysis and whitepaper-style reports.
"""

import json
import logging
import statistics
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from .models import (
    ComparisonReport, BenchmarkConfig, BenchmarkResult, BenchmarkTask,
    ModelResponse, EvaluationResult, EvaluationDimension, TaskStatistics,
    DomainAnalysis
)

logger = logging.getLogger(__name__)


class StatisticsCollector:
    """Collector for statistical analysis of benchmark results."""
    
    @staticmethod
    def calculate_task_statistics(task_id: str, responses: List[ModelResponse], 
                                evaluations: List[EvaluationResult]) -> TaskStatistics:
        """Calculate statistics for a specific task."""
        if not responses:
            return TaskStatistics(
                task_id=task_id,
                domain="unknown",
                subdomain="unknown",
                model_responses=0,
                successful_responses=0,
                failed_responses=0,
                mean_score=0,
                median_score=0,
                std_score=0,
                min_score=0,
                max_score=0,
                attribute_accuracy=0,
                skill_accuracy=0,
                difficulty_accuracy=0,
                formula_accuracy=0,
                score_variance=0,
                inter_model_agreement=0,
                estimated_difficulty=0
            )
        
        # Basic response stats
        total_responses = len(responses)
        successful_responses = sum(1 for r in responses if r.successful_parse)
        failed_responses = total_responses - successful_responses
        
        # Score statistics from evaluations
        scores = [e.overall_score for e in evaluations if e.overall_score is not None]
        if scores:
            mean_score = statistics.mean(scores)
            median_score = statistics.median(scores)
            std_score = statistics.stdev(scores) if len(scores) > 1 else 0
            min_score = min(scores)
            max_score = max(scores)
            score_variance = statistics.variance(scores) if len(scores) > 1 else 0
        else:
            mean_score = median_score = std_score = min_score = max_score = score_variance = 0
        
        # Accuracy metrics
        attribute_correct = sum(1 for e in evaluations if e.attribute_correct)
        skill_correct = sum(1 for e in evaluations if e.skill_correct)
        difficulty_correct = sum(1 for e in evaluations if e.difficulty_within_range)
        formula_correct = sum(1 for e in evaluations if e.formula_correct)
        
        total_evals = len(evaluations) or 1
        attribute_accuracy = attribute_correct / total_evals
        skill_accuracy = skill_correct / total_evals
        difficulty_accuracy = difficulty_correct / total_evals
        formula_accuracy = formula_correct / total_evals
        
        # Inter-model agreement (simplified as inverse of score variance)
        inter_model_agreement = 1 / (1 + score_variance) if score_variance > 0 else 1
        
        # Estimate difficulty based on performance
        estimated_difficulty = 1 - mean_score / 10 if mean_score > 0 else 1
        
        return TaskStatistics(
            task_id=task_id,
            domain="unknown",  # Would need task info
            subdomain="unknown",
            model_responses=total_responses,
            successful_responses=successful_responses,
            failed_responses=failed_responses,
            mean_score=mean_score,
            median_score=median_score,
            std_score=std_score,
            min_score=min_score,
            max_score=max_score,
            attribute_accuracy=attribute_accuracy,
            skill_accuracy=skill_accuracy,
            difficulty_accuracy=difficulty_accuracy,
            formula_accuracy=formula_accuracy,
            score_variance=score_variance,
            inter_model_agreement=inter_model_agreement,
            estimated_difficulty=estimated_difficulty
        )
    
    @staticmethod
    def analyze_domain_performance(domain: str, subdomain: str, 
                                 results: List[BenchmarkResult]) -> DomainAnalysis:
        """Analyze performance for a specific domain."""
        domain_key = f"{domain}.{subdomain}"
        
        # Collect scores for this domain
        domain_scores = {}
        total_tasks = 0
        
        for result in results:
            if domain_key in result.domain_performance:
                domain_data = result.domain_performance[domain_key]
                domain_scores[result.model_name] = domain_data.get('average_score', 0)
                total_tasks = max(total_tasks, domain_data.get('count', 0))
        
        # Calculate rankings
        model_rankings = {}
        sorted_models = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
        for i, (model_name, score) in enumerate(sorted_models):
            model_rankings[model_name] = i + 1
        
        # Analyze strengths and weaknesses
        strengths = []
        weaknesses = []
        recommendations = []
        
        if domain_scores:
            avg_score = statistics.mean(domain_scores.values())
            if avg_score > 7:
                strengths.append("Strong overall performance in this domain")
            elif avg_score < 5:
                weaknesses.append("Weak overall performance in this domain")
            
            score_variance = statistics.variance(domain_scores.values()) if len(domain_scores) > 1 else 0
            if score_variance > 2:
                weaknesses.append("High variance between models")
                recommendations.append("Further analysis needed to understand model differences")
        
        return DomainAnalysis(
            domain=domain,
            subdomain=subdomain,
            total_tasks=total_tasks,
            average_scores=domain_scores,
            model_rankings=model_rankings,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendations=recommendations
        )
    
    @staticmethod
    def calculate_correlation_matrix(results: List[BenchmarkResult]) -> Dict[str, Dict[str, float]]:
        """Calculate correlation matrix between different evaluation dimensions."""
        correlations = {}
        
        # Collect dimension scores for all models
        dimension_data = {dim: [] for dim in EvaluationDimension}
        
        for result in results:
            for dimension in EvaluationDimension:
                score = result.dimension_scores.get(dimension, 0)
                dimension_data[dimension].append(score)
        
        # Calculate correlations between dimensions
        for dim1 in EvaluationDimension:
            correlations[dim1.value] = {}
            for dim2 in EvaluationDimension:
                if len(dimension_data[dim1]) > 1 and len(dimension_data[dim2]) > 1:
                    # Simple correlation coefficient calculation
                    corr = StatisticsCollector._calculate_correlation(
                        dimension_data[dim1], dimension_data[dim2]
                    )
                    correlations[dim1.value][dim2.value] = corr
                else:
                    correlations[dim1.value][dim2.value] = 0
        
        return correlations
    
    @staticmethod
    def _calculate_correlation(x: List[float], y: List[float]) -> float:
        """Calculate Pearson correlation coefficient."""
        if len(x) != len(y) or len(x) < 2:
            return 0
        
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_x2 = sum(xi**2 for xi in x)
        sum_y2 = sum(yi**2 for yi in y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        
        numerator = n * sum_xy - sum_x * sum_y
        denominator = ((n * sum_x2 - sum_x**2) * (n * sum_y2 - sum_y**2))**0.5
        
        if denominator == 0:
            return 0
        
        return numerator / denominator


class WhitepaperGenerator:
    """Generator for comprehensive whitepaper-style reports."""
    
    def generate_whitepaper(self, 
                          comparison_report: ComparisonReport,
                          config: BenchmarkConfig,
                          task_responses: Dict[str, List[ModelResponse]],
                          evaluations: Dict[str, List[EvaluationResult]]) -> str:
        """Generate a comprehensive whitepaper report."""
        
        # Calculate additional statistics
        stats_collector = StatisticsCollector()
        
        # Generate whitepaper content
        content = self._generate_header(comparison_report, config)
        content += self._generate_executive_summary(comparison_report)
        content += self._generate_methodology_section(config)
        content += self._generate_results_section(comparison_report, task_responses, evaluations)
        content += self._generate_analysis_section(comparison_report, stats_collector)
        content += self._generate_domain_analysis_section(comparison_report)
        content += self._generate_conclusions_section(comparison_report)
        content += self._generate_appendices(comparison_report, task_responses)
        
        return content
    
    def _generate_header(self, report: ComparisonReport, config: BenchmarkConfig) -> str:
        """Generate whitepaper header and metadata."""
        return f"""# Aeonisk YAGS Language Model Benchmark Report

**Benchmark Name:** {report.benchmark_name}  
**Dataset Version:** {report.dataset_version}  
**Generated:** {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}  
**Total Tasks:** {report.total_tasks}  
**Models Evaluated:** {len(report.models)}  

## Abstract

This report presents a comprehensive evaluation of {len(report.models)} language models on Aeonisk YAGS gameplay tasks. The benchmark evaluates models across multiple dimensions including mechanical accuracy, narrative quality, rules adherence, and creative output. Results show significant variations in model performance across different aspects of tabletop RPG gameplay assistance.

---

"""
    
    def _generate_executive_summary(self, report: ComparisonReport) -> str:
        """Generate executive summary section."""
        top_model = list(report.model_rankings.keys())[0] if report.model_rankings else "Unknown"
        
        return f"""## Executive Summary

### Key Findings

- **Top Performing Model:** {top_model}
- **Total Tasks Evaluated:** {report.total_tasks}
- **Models Compared:** {', '.join(report.models)}

### Performance Highlights

The benchmark revealed significant differences in how language models handle tabletop RPG mechanics and narrative generation. Key observations include:

1. **Mechanical Accuracy:** Models showed varying ability to correctly apply YAGS rule mechanics
2. **Narrative Quality:** Significant differences in creative and thematically appropriate content generation
3. **Consistency:** Some models showed high variance in performance across similar tasks
4. **Domain Specialization:** Certain models performed better in specific gameplay domains

### Recommendations

Based on the evaluation results, we recommend:

- For mechanical accuracy: Consider {top_model} for rules-based queries
- For narrative creativity: Evaluate models based on specific creative requirements
- For general gameplay assistance: Balance between accuracy and creativity is crucial

---

"""
    
    def _generate_methodology_section(self, config: BenchmarkConfig) -> str:
        """Generate methodology section."""
        return f"""## Methodology

### Dataset

The benchmark utilizes the Aeonisk YAGS normalized dataset containing {config.sample_size or 'all available'} gameplay scenarios. Each scenario includes:

- **Scenario Description:** Narrative setup and character context
- **Gold Standard Answers:** Expert-validated responses including:
  - Attribute and skill selection
  - Roll formulas and difficulty assessments
  - Six-tier outcome explanations (Critical Failure to Exceptional Success)
  - Mechanical consequences and narrative descriptions

### Evaluation Framework

#### Automated Metrics
- **Attribute Accuracy:** Correctness of primary attribute selection
- **Skill Accuracy:** Appropriateness of skill choice
- **Formula Accuracy:** Mathematical correctness of roll calculations
- **Difficulty Assessment:** Appropriateness of target numbers

#### AI Judge Evaluation
{f'AI evaluation performed using {config.judge_model}' if config.use_ai_judge else 'AI evaluation disabled for this benchmark'}

Evaluation dimensions:
- **Mechanical Accuracy (1-10):** Adherence to YAGS core mechanics
- **Narrative Quality (1-10):** Engagement and thematic appropriateness
- **Rules Adherence (1-10):** Correct application of Aeonisk-specific rules
- **Consistency (1-10):** Internal logical coherence
- **Creativity (1-10):** Novel and interesting outcomes
- **Difficulty Appropriateness (1-10):** Well-calibrated challenge assessment
- **Overall Quality (1-10):** General usability in actual gameplay

### Models Evaluated

{self._format_model_list(config.models)}

### Limitations

- Evaluation is based on text-only responses without actual gameplay testing
- AI judge may have inherent biases toward certain response styles
- Dataset may not cover all possible Aeonisk gameplay scenarios
- Inter-rater reliability not established for subjective metrics

---

"""
    
    def _format_model_list(self, models: List[Dict[str, Any]]) -> str:
        """Format the list of models for the methodology section."""
        model_list = ""
        for model in models:
            provider = model.get('provider', 'unknown')
            model_name = model.get('model', 'unknown')
            model_list += f"- **{provider.title()}:** {model_name}\n"
        return model_list
    
    def _generate_results_section(self, 
                                report: ComparisonReport,
                                task_responses: Dict[str, List[ModelResponse]],
                                evaluations: Dict[str, List[EvaluationResult]]) -> str:
        """Generate detailed results section."""
        content = "## Results\n\n"
        
        # Overall rankings
        content += "### Overall Model Rankings\n\n"
        content += "| Rank | Model | Overall Score | Success Rate |\n"
        content += "|------|-------|---------------|-------------|\n"
        
        for i, result in enumerate(report.results):
            rank = report.model_rankings.get(result.model_name, i + 1)
            content += f"| {rank} | {result.model_name} | {result.overall_score:.2f} | {result.success_rate:.1%} |\n"
        
        content += "\n"
        
        # Dimension analysis
        content += "### Performance by Evaluation Dimension\n\n"
        for dimension in EvaluationDimension:
            content += f"#### {dimension.value.replace('_', ' ').title()}\n\n"
            content += "| Model | Score | Rank |\n"
            content += "|-------|-------|------|\n"
            
            if dimension in report.dimension_rankings:
                rankings = report.dimension_rankings[dimension]
                # Sort by rank
                sorted_rankings = sorted(rankings.items(), key=lambda x: x[1])
                for model, rank in sorted_rankings:
                    # Find score for this model and dimension
                    score = 0
                    for result in report.results:
                        if result.model_name == model:
                            score = result.dimension_scores.get(dimension, 0)
                            break
                    content += f"| {model} | {score:.2f} | {rank} |\n"
            
            content += "\n"
        
        # Response time analysis
        content += "### Performance Metrics\n\n"
        content += "| Model | Avg Response Time (s) | Total Tokens | Completed Tasks |\n"
        content += "|-------|----------------------|--------------|----------------|\n"
        
        for result in report.results:
            tokens = result.total_tokens if result.total_tokens else "N/A"
            content += f"| {result.model_name} | {result.average_response_time:.2f} | {tokens} | {result.completed_tasks}/{result.total_tasks} |\n"
        
        content += "\n---\n\n"
        return content
    
    def _generate_analysis_section(self, 
                                 report: ComparisonReport,
                                 stats_collector: StatisticsCollector) -> str:
        """Generate statistical analysis section."""
        content = "## Statistical Analysis\n\n"
        
        # Model comparison
        content += "### Model Performance Comparison\n\n"
        content += "Detailed analysis of model performance reveals several key patterns:\n\n"
        
        # Top vs bottom performers
        if len(report.results) >= 2:
            top_model = max(report.results, key=lambda x: x.overall_score)
            bottom_model = min(report.results, key=lambda x: x.overall_score)
            
            content += f"**Highest Performer:** {top_model.model_name} (Overall Score: {top_model.overall_score:.2f})\n"
            content += f"**Lowest Performer:** {bottom_model.model_name} (Overall Score: {bottom_model.overall_score:.2f})\n"
            content += f"**Performance Gap:** {top_model.overall_score - bottom_model.overall_score:.2f} points\n\n"
        
        # Performance distribution
        scores = [result.overall_score for result in report.results]
        if scores:
            mean_score = statistics.mean(scores)
            median_score = statistics.median(scores)
            std_score = statistics.stdev(scores) if len(scores) > 1 else 0
            
            content += f"**Mean Score:** {mean_score:.2f}\n"
            content += f"**Median Score:** {median_score:.2f}\n"
            content += f"**Standard Deviation:** {std_score:.2f}\n\n"
        
        # Correlation analysis
        if len(report.results) > 2:
            correlations = stats_collector.calculate_correlation_matrix(report.results)
            content += "### Dimension Correlations\n\n"
            content += "Analysis of correlations between evaluation dimensions:\n\n"
            
            # Find strongest correlations
            strong_correlations = []
            for dim1, corr_dict in correlations.items():
                for dim2, corr in corr_dict.items():
                    if dim1 != dim2 and abs(corr) > 0.5:  # Strong correlation threshold
                        strong_correlations.append((dim1, dim2, corr))
            
            if strong_correlations:
                content += "**Strong Correlations (|r| > 0.5):**\n"
                for dim1, dim2, corr in sorted(strong_correlations, key=lambda x: abs(x[2]), reverse=True):
                    content += f"- {dim1.replace('_', ' ').title()} ↔ {dim2.replace('_', ' ').title()}: r = {corr:.3f}\n"
                content += "\n"
        
        content += "---\n\n"
        return content
    
    def _generate_domain_analysis_section(self, report: ComparisonReport) -> str:
        """Generate domain-specific analysis section."""
        content = "## Domain-Specific Analysis\n\n"
        
        if not report.domain_comparisons:
            content += "No domain-specific data available.\n\n"
            return content
        
        content += "Performance analysis by gameplay domain:\n\n"
        
        for domain, scores in report.domain_comparisons.items():
            content += f"### {domain.replace('.', ' - ').replace('_', ' ').title()}\n\n"
            
            # Sort models by score for this domain
            sorted_models = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            
            content += "| Rank | Model | Score |\n"
            content += "|------|-------|-------|\n"
            
            for i, (model, score) in enumerate(sorted_models):
                content += f"| {i+1} | {model} | {score:.2f} |\n"
            
            content += "\n"
            
            # Analysis
            if scores:
                avg_score = statistics.mean(scores.values())
                best_model = sorted_models[0][0]
                content += f"**Domain Average:** {avg_score:.2f}\n"
                content += f"**Top Performer:** {best_model}\n"
                
                if avg_score > 7:
                    content += "**Assessment:** Strong performance across models in this domain.\n"
                elif avg_score < 5:
                    content += "**Assessment:** This domain presents significant challenges for most models.\n"
                else:
                    content += "**Assessment:** Moderate performance with room for improvement.\n"
            
            content += "\n"
        
        content += "---\n\n"
        return content
    
    def _generate_conclusions_section(self, report: ComparisonReport) -> str:
        """Generate conclusions and recommendations section."""
        content = "## Conclusions and Recommendations\n\n"
        
        # Key findings
        content += "### Key Findings\n\n"
        
        if report.results:
            top_model = max(report.results, key=lambda x: x.overall_score)
            content += f"1. **{top_model.model_name}** demonstrated the strongest overall performance with a score of {top_model.overall_score:.2f}\n"
            
            # Find best dimension for top model
            best_dimension = max(top_model.dimension_scores.items(), key=lambda x: x[1])
            content += f"2. The top model excelled particularly in {best_dimension[0].value.replace('_', ' ')} (score: {best_dimension[1]:.2f})\n"
            
            # Performance gaps
            scores = [r.overall_score for r in report.results]
            if len(scores) > 1:
                score_range = max(scores) - min(scores)
                content += f"3. Performance gap between best and worst models: {score_range:.2f} points\n"
        
        # Domain insights
        if report.domain_comparisons:
            domain_averages = {domain: statistics.mean(scores.values()) 
                             for domain, scores in report.domain_comparisons.items()}
            if domain_averages:
                easiest_domain = max(domain_averages.items(), key=lambda x: x[1])
                hardest_domain = min(domain_averages.items(), key=lambda x: x[1])
                
                content += f"4. Easiest domain: {easiest_domain[0]} (avg score: {easiest_domain[1]:.2f})\n"
                content += f"5. Most challenging domain: {hardest_domain[0]} (avg score: {hardest_domain[1]:.2f})\n"
        
        content += "\n"
        
        # Recommendations
        content += "### Recommendations\n\n"
        content += "Based on this comprehensive evaluation:\n\n"
        
        content += "#### For Game Masters\n"
        if report.results:
            top_model = max(report.results, key=lambda x: x.overall_score)
            content += f"- Consider **{top_model.model_name}** for general gameplay assistance\n"
            content += "- Evaluate models based on your specific needs (mechanics vs. narrative)\n"
            content += "- Always verify rule interpretations against official sources\n\n"
        
        content += "#### For Model Developers\n"
        content += "- Focus on improving mechanical accuracy and rules adherence\n"
        content += "- Enhance understanding of tabletop RPG conventions\n"
        content += "- Consider specialized training on game rule systems\n\n"
        
        content += "#### For Future Research\n"
        content += "- Expand evaluation to include actual gameplay testing\n"
        content += "- Develop more sophisticated evaluation metrics\n"
        content += "- Include human expert evaluations for validation\n\n"
        
        content += "---\n\n"
        return content
    
    def _generate_appendices(self, 
                           report: ComparisonReport,
                           task_responses: Dict[str, List[ModelResponse]]) -> str:
        """Generate appendices with detailed data."""
        content = "## Appendices\n\n"
        
        # Appendix A: Model Configurations
        content += "### Appendix A: Model Configurations\n\n"
        content += "Detailed configuration information for each evaluated model:\n\n"
        
        for result in report.results:
            content += f"#### {result.model_name}\n"
            content += f"- **Provider:** {result.provider}\n"
            content += f"- **Total Tasks:** {result.total_tasks}\n"
            content += f"- **Success Rate:** {result.success_rate:.1%}\n"
            content += f"- **Average Response Time:** {result.average_response_time:.2f}s\n"
            if result.total_tokens:
                content += f"- **Total Tokens:** {result.total_tokens:,}\n"
            content += "\n"
        
        # Appendix B: Statistical Details
        content += "### Appendix B: Statistical Details\n\n"
        content += f"- **Benchmark Generated:** {report.generated_at}\n"
        content += f"- **Total Tasks:** {report.total_tasks}\n"
        content += f"- **Models Evaluated:** {len(report.models)}\n"
        content += f"- **Dataset Version:** {report.dataset_version}\n\n"
        
        # Task distribution
        if task_responses:
            content += f"**Task Distribution:**\n"
            content += f"- Total unique tasks: {len(task_responses)}\n"
            total_responses = sum(len(responses) for responses in task_responses.values())
            content += f"- Total responses generated: {total_responses}\n"
            content += f"- Average responses per task: {total_responses / len(task_responses):.1f}\n\n"
        
        content += "---\n\n"
        content += "*End of Report*"
        
        return content