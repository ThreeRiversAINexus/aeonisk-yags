"""
AI Judge and evaluation system for the Aeonisk YAGS benchmarking framework.

This module provides comprehensive evaluation of model responses using both
automated metrics and AI-based judgment.
"""

import asyncio
import json
import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import openai
from openai import OpenAI

from .models import (
    BenchmarkTask, ModelResponse, EvaluationResult, EvaluationDimension
)

logger = logging.getLogger(__name__)


class EvaluationMetrics:
    """Automated evaluation metrics for model responses."""
    
    @staticmethod
    def calculate_attribute_accuracy(response: ModelResponse, gold_answer: Dict[str, Any]) -> bool:
        """Check if the chosen attribute matches the gold standard."""
        if not response.attribute_used or not gold_answer.get('attribute_used'):
            return False
        
        # Normalize attribute names for comparison
        response_attr = response.attribute_used.lower().strip()
        gold_attr = gold_answer['attribute_used'].lower().strip()
        
        # Handle common variations
        attr_aliases = {
            'str': 'strength',
            'dex': 'dexterity',
            'agi': 'agility',
            'int': 'intelligence',
            'per': 'perception',
            'wil': 'willpower',
            'emp': 'empathy',
            'hea': 'health'
        }
        
        # Check direct match
        if response_attr == gold_attr:
            return True
        
        # Check aliases
        response_attr = attr_aliases.get(response_attr, response_attr)
        gold_attr = attr_aliases.get(gold_attr, gold_attr)
        
        return response_attr == gold_attr
    
    @staticmethod
    def calculate_skill_accuracy(response: ModelResponse, gold_answer: Dict[str, Any]) -> bool:
        """Check if the chosen skill matches the gold standard."""
        if not response.skill_used or not gold_answer.get('skill_used'):
            return False
        
        # Normalize skill names for comparison
        response_skill = response.skill_used.lower().strip().replace('_', ' ')
        gold_skill = gold_answer['skill_used'].lower().strip().replace('_', ' ')
        
        # Handle common variations
        skill_aliases = {
            'athletics': 'athletics',
            'astral arts': 'astral_arts',
            'magick theory': 'magick_theory',
            'lore biotech': 'lore_biotech',
            'corporate influence': 'corporate_influence',
            'debt law': 'debt_law',
            'intimacy ritual': 'intimacy_ritual'
        }
        
        # Check direct match
        if response_skill == gold_skill:
            return True
        
        # Check aliases
        response_skill = skill_aliases.get(response_skill, response_skill)
        gold_skill = skill_aliases.get(gold_skill, gold_skill)
        
        return response_skill == gold_skill
    
    @staticmethod
    def calculate_difficulty_accuracy(response: ModelResponse, gold_answer: Dict[str, Any]) -> bool:
        """Check if the difficulty is within reasonable range of gold standard."""
        if not response.difficulty_guess or not gold_answer.get('difficulty_guess'):
            return False
        
        response_diff = response.difficulty_guess
        gold_diff = gold_answer['difficulty_guess']
        
        # Allow for ±3 variance in difficulty assessment
        return abs(response_diff - gold_diff) <= 3
    
    @staticmethod
    def calculate_formula_accuracy(response: ModelResponse, gold_answer: Dict[str, Any]) -> bool:
        """Check if the roll formula follows correct YAGS mechanics."""
        if not response.roll_formula or not gold_answer.get('roll_formula'):
            return False
        
        # Extract components from formula
        formula_pattern = r'(\w+)\s*(\d+)\s*[x×]\s*(\w+)\s*(\d+)\s*=\s*(\d+)'
        
        response_match = re.search(formula_pattern, response.roll_formula)
        gold_match = re.search(formula_pattern, gold_answer['roll_formula'])
        
        if not response_match or not gold_match:
            return False
        
        # Check if the calculation is correct
        resp_attr_val = int(response_match.group(2))
        resp_skill_val = int(response_match.group(4))
        resp_result = int(response_match.group(5))
        
        gold_attr_val = int(gold_match.group(2))
        gold_skill_val = int(gold_match.group(4))
        gold_result = int(gold_match.group(5))
        
        # Formula should be mathematically correct
        return (resp_attr_val * resp_skill_val == resp_result and
                gold_attr_val * gold_skill_val == gold_result)
    
    @staticmethod
    def calculate_outcome_completeness(response: ModelResponse, gold_answer: Dict[str, Any]) -> float:
        """Calculate how complete the outcome explanations are."""
        if not response.outcome_explanation:
            return 0.0
        
        expected_outcomes = [
            'critical_failure', 'failure', 'moderate_success',
            'good_success', 'excellent_success', 'exceptional_success'
        ]
        
        present_outcomes = 0
        for outcome in expected_outcomes:
            if outcome in response.outcome_explanation:
                outcome_data = response.outcome_explanation[outcome]
                if isinstance(outcome_data, dict):
                    if outcome_data.get('narrative') and outcome_data.get('mechanical_effect'):
                        present_outcomes += 1
        
        return present_outcomes / len(expected_outcomes)
    
    @staticmethod
    def calculate_overall_accuracy(response: ModelResponse, gold_answer: Dict[str, Any]) -> float:
        """Calculate overall accuracy score."""
        scores = []
        
        # Individual component scores
        attr_correct = EvaluationMetrics.calculate_attribute_accuracy(response, gold_answer)
        skill_correct = EvaluationMetrics.calculate_skill_accuracy(response, gold_answer)
        diff_correct = EvaluationMetrics.calculate_difficulty_accuracy(response, gold_answer)
        formula_correct = EvaluationMetrics.calculate_formula_accuracy(response, gold_answer)
        outcome_complete = EvaluationMetrics.calculate_outcome_completeness(response, gold_answer)
        
        # Weight the scores
        weighted_score = (
            attr_correct * 0.2 +
            skill_correct * 0.2 +
            diff_correct * 0.2 +
            formula_correct * 0.2 +
            outcome_complete * 0.2
        )
        
        return weighted_score


class AIJudge:
    """AI-powered judge for evaluating model responses."""
    
    def __init__(self, judge_model: str = "gpt-4", api_key: str = None):
        """Initialize the AI judge."""
        self.judge_model = judge_model
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key) if api_key else None
        self.metrics = EvaluationMetrics()
    
    def create_evaluation_prompt(self, task: BenchmarkTask, response: ModelResponse) -> str:
        """Create evaluation prompt for the AI judge."""
        prompt = f"""You are an expert evaluator of tabletop RPG responses, specifically for the Aeonisk YAGS system. Your task is to evaluate how well a language model responded to a gameplay scenario.

ORIGINAL TASK:
Scenario: {task.scenario}
Environment: {task.environment}
Stakes: {task.stakes}
Goal: {task.goal}

GOLD STANDARD ANSWER:
{json.dumps(task.gold_answer, indent=2)}

MODEL RESPONSE:
{response.raw_response}

EVALUATION CRITERIA:
Rate each dimension on a scale of 1-10:

1. **Mechanical Accuracy (1-10)**: How accurately did the model apply YAGS mechanics?
   - Correct attribute selection
   - Correct skill selection
   - Proper roll formula (Attribute × Skill = Base; Base + d20)
   - Appropriate difficulty assessment

2. **Narrative Quality (1-10)**: How engaging and thematically appropriate are the narratives?
   - Vivid, immersive descriptions
   - Consistent tone with Aeonisk setting
   - Appropriate escalation between outcome levels

3. **Rules Adherence (1-10)**: How well did the model follow YAGS and Aeonisk rules?
   - Correct understanding of Void mechanics
   - Proper use of Soulcredit system
   - Accurate wound and condition handling

4. **Consistency (1-10)**: How internally consistent is the response?
   - Logical progression of outcomes
   - Consistent character abilities
   - Coherent cause-and-effect relationships

5. **Creativity (1-10)**: How creative and interesting are the outcomes?
   - Novel but appropriate consequences
   - Engaging complications and benefits
   - Memorable narrative moments

6. **Difficulty Appropriateness (1-10)**: How well-calibrated is the difficulty assessment?
   - Matches task complexity
   - Appropriate for character capabilities
   - Consistent with YAGS difficulty guidelines

7. **Overall Quality (1-10)**: General assessment of response quality
   - Would you use this response in an actual game?
   - Does it enhance the gaming experience?

RESPONSE FORMAT:
Please provide your evaluation in the following JSON format:

{{
    "scores": {{
        "mechanical_accuracy": X,
        "narrative_quality": X,
        "rules_adherence": X,
        "consistency": X,
        "creativity": X,
        "difficulty_appropriate": X,
        "overall_quality": X
    }},
    "comments": {{
        "mechanical_accuracy": "Brief explanation of score",
        "narrative_quality": "Brief explanation of score",
        "rules_adherence": "Brief explanation of score",
        "consistency": "Brief explanation of score",
        "creativity": "Brief explanation of score",
        "difficulty_appropriate": "Brief explanation of score",
        "overall_quality": "Brief explanation of score"
    }},
    "overall_score": X,
    "gold_standard_similarity": X,
    "judge_rationale": "Overall assessment and key observations",
    "attribute_correct": true/false,
    "skill_correct": true/false,
    "difficulty_within_range": true/false,
    "formula_correct": true/false,
    "outcomes_plausible": true/false
}}

Be thorough but concise in your evaluation. Focus on how well the response would work in an actual game session.
"""
        return prompt
    
    async def evaluate_response(self, task: BenchmarkTask, response: ModelResponse) -> EvaluationResult:
        """Evaluate a model response using AI judgment."""
        try:
            # First, calculate automated metrics
            automated_metrics = self._calculate_automated_metrics(response, task.gold_answer)
            
            # If no API client, use only automated metrics
            if not self.client:
                return EvaluationResult(
                    task_id=task.task_id,
                    model_name=response.model_name,
                    overall_score=automated_metrics['overall_score'],
                    gold_standard_similarity=automated_metrics['gold_standard_similarity'],
                    judge_rationale="Automated evaluation only - no AI judge available",
                    **automated_metrics
                )
            
            # Generate AI evaluation
            prompt = self.create_evaluation_prompt(task, response)
            
            ai_response = self.client.chat.completions.create(
                model=self.judge_model,
                messages=[
                    {"role": "system", "content": "You are an expert tabletop RPG evaluator specializing in the Aeonisk YAGS system."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=1500
            )
            
            # Parse AI response
            ai_evaluation = self._parse_ai_evaluation(ai_response.choices[0].message.content)
            
            # Combine automated and AI metrics
            combined_evaluation = self._combine_evaluations(automated_metrics, ai_evaluation)
            
            return EvaluationResult(
                task_id=task.task_id,
                model_name=response.model_name,
                **combined_evaluation
            )
            
        except Exception as e:
            logger.error(f"Error evaluating response: {e}")
            # Fallback to automated metrics only
            automated_metrics = self._calculate_automated_metrics(response, task.gold_answer)
            return EvaluationResult(
                task_id=task.task_id,
                model_name=response.model_name,
                judge_rationale=f"Evaluation error: {str(e)}",
                **automated_metrics
            )
    
    def _calculate_automated_metrics(self, response: ModelResponse, gold_answer: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate automated evaluation metrics."""
        return {
            'attribute_correct': self.metrics.calculate_attribute_accuracy(response, gold_answer),
            'skill_correct': self.metrics.calculate_skill_accuracy(response, gold_answer),
            'difficulty_within_range': self.metrics.calculate_difficulty_accuracy(response, gold_answer),
            'formula_correct': self.metrics.calculate_formula_accuracy(response, gold_answer),
            'outcomes_plausible': self.metrics.calculate_outcome_completeness(response, gold_answer) > 0.5,
            'overall_score': self.metrics.calculate_overall_accuracy(response, gold_answer) * 10,
            'gold_standard_similarity': self.metrics.calculate_overall_accuracy(response, gold_answer)
        }
    
    def _parse_ai_evaluation(self, ai_response: str) -> Dict[str, Any]:
        """Parse AI evaluation response."""
        try:
            # Extract JSON from the response
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                evaluation = json.loads(json_str)
                return evaluation
            else:
                logger.warning("No JSON found in AI evaluation response")
                return {}
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing AI evaluation JSON: {e}")
            return {}
    
    def _combine_evaluations(self, automated: Dict[str, Any], ai_eval: Dict[str, Any]) -> Dict[str, Any]:
        """Combine automated and AI evaluations."""
        combined = automated.copy()
        
        # Use AI scores if available, otherwise use automated
        if 'scores' in ai_eval:
            scores = {}
            for dimension in EvaluationDimension:
                ai_score = ai_eval['scores'].get(dimension.value, 0)
                scores[dimension] = ai_score if ai_score > 0 else combined.get('overall_score', 0)
            combined['scores'] = scores
        
        # Use AI comments if available
        if 'comments' in ai_eval:
            combined['comments'] = ai_eval['comments']
        
        # Use AI overall assessment if available
        if 'overall_score' in ai_eval:
            combined['overall_score'] = ai_eval['overall_score']
        
        if 'gold_standard_similarity' in ai_eval:
            combined['gold_standard_similarity'] = ai_eval['gold_standard_similarity']
        
        if 'judge_rationale' in ai_eval:
            combined['judge_rationale'] = ai_eval['judge_rationale']
        
        # Override boolean flags with AI assessment if available
        for flag in ['attribute_correct', 'skill_correct', 'difficulty_within_range', 'formula_correct', 'outcomes_plausible']:
            if flag in ai_eval:
                combined[flag] = ai_eval[flag]
        
        return combined
    
    async def evaluate_batch(self, tasks_and_responses: List[Tuple[BenchmarkTask, ModelResponse]]) -> List[EvaluationResult]:
        """Evaluate multiple responses in batch."""
        results = []
        
        # Process in batches to avoid rate limiting
        batch_size = 5
        for i in range(0, len(tasks_and_responses), batch_size):
            batch = tasks_and_responses[i:i + batch_size]
            
            # Create evaluation tasks
            eval_tasks = []
            for task, response in batch:
                eval_tasks.append(self.evaluate_response(task, response))
            
            # Run batch evaluation
            batch_results = await asyncio.gather(*eval_tasks, return_exceptions=True)
            
            # Process results
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"Batch evaluation error: {result}")
                else:
                    results.append(result)
            
            # Rate limiting delay
            await asyncio.sleep(1)
        
        return results


class ComparisonAnalyzer:
    """Analyzer for comparing multiple model responses."""
    
    @staticmethod
    def analyze_response_diversity(responses: List[ModelResponse]) -> Dict[str, Any]:
        """Analyze diversity of responses across models."""
        if not responses:
            return {}
        
        # Collect attributes used
        attributes = [r.attribute_used for r in responses if r.attribute_used]
        skills = [r.skill_used for r in responses if r.skill_used]
        difficulties = [r.difficulty_guess for r in responses if r.difficulty_guess]
        
        # Calculate diversity metrics
        unique_attributes = len(set(attributes))
        unique_skills = len(set(skills))
        difficulty_range = max(difficulties) - min(difficulties) if difficulties else 0
        
        return {
            'total_responses': len(responses),
            'unique_attributes': unique_attributes,
            'unique_skills': unique_skills,
            'difficulty_range': difficulty_range,
            'attribute_distribution': {attr: attributes.count(attr) for attr in set(attributes)},
            'skill_distribution': {skill: skills.count(skill) for skill in set(skills)},
            'difficulty_stats': {
                'min': min(difficulties) if difficulties else 0,
                'max': max(difficulties) if difficulties else 0,
                'mean': sum(difficulties) / len(difficulties) if difficulties else 0
            }
        }
    
    @staticmethod
    def identify_consensus_and_outliers(responses: List[ModelResponse]) -> Dict[str, Any]:
        """Identify consensus answers and outliers."""
        if not responses:
            return {}
        
        # Find most common attribute and skill
        attributes = [r.attribute_used for r in responses if r.attribute_used]
        skills = [r.skill_used for r in responses if r.skill_used]
        
        most_common_attr = max(set(attributes), key=attributes.count) if attributes else None
        most_common_skill = max(set(skills), key=skills.count) if skills else None
        
        # Find outliers (responses that differ significantly from consensus)
        outliers = []
        for response in responses:
            if (response.attribute_used != most_common_attr or 
                response.skill_used != most_common_skill):
                outliers.append(response.model_name)
        
        return {
            'consensus_attribute': most_common_attr,
            'consensus_skill': most_common_skill,
            'outlier_models': outliers,
            'consensus_strength': (
                (attributes.count(most_common_attr) if most_common_attr else 0) +
                (skills.count(most_common_skill) if most_common_skill else 0)
            ) / (len(responses) * 2) if responses else 0
        }