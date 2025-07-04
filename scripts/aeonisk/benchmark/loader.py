"""
Dataset loader for the Aeonisk YAGS benchmarking system.

This module handles loading and parsing of the normalized dataset files.
"""

import os
import yaml
import json
import logging
import re
from typing import Dict, List, Optional, Iterator, Any
from pathlib import Path

from .models import BenchmarkTask, TaskDomain

logger = logging.getLogger(__name__)


class TaskParser:
    """Parser for individual task entries in the dataset."""
    
    @staticmethod
    def parse_yaml_entry(entry_text: str) -> Optional[Dict[str, Any]]:
        """Parse a single YAML entry from the dataset."""
        try:
            # Remove the leading --- separator if present
            entry_text = entry_text.strip()
            if entry_text.startswith('---'):
                entry_text = entry_text[3:].strip()
            
            # Parse the YAML
            data = yaml.safe_load(entry_text)
            return data
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing entry: {e}")
            return None
    
    @staticmethod
    def extract_task_fields(data: Dict[str, Any]) -> Optional[BenchmarkTask]:
        """Extract and validate task fields from parsed data."""
        try:
            # Required fields
            task_id = data.get('task_id')
            if not task_id:
                logger.warning("Task missing task_id")
                return None
            
            domain_data = data.get('domain', {})
            domain = TaskDomain(
                core=domain_data.get('core', 'unknown'),
                subdomain=domain_data.get('subdomain', 'unknown')
            )
            
            # Create the BenchmarkTask
            task = BenchmarkTask(
                task_id=task_id,
                domain=domain,
                scenario=data.get('scenario', ''),
                environment=data.get('environment', ''),
                stakes=data.get('stakes', ''),
                characters=data.get('characters', []),
                goal=data.get('goal', ''),
                expected_fields=data.get('expected_fields', []),
                gold_answer=data.get('gold_answer', {}),
                aeonisk_extra_data=data.get('aeonisk_extra_data')
            )
            
            # Extract metadata
            if 'aeonisk_extra_data' in data:
                extra_data = data['aeonisk_extra_data']
                if isinstance(extra_data, dict):
                    task.tags = extra_data.get('tags', [])
                    task.difficulty_level = extra_data.get('difficulty_level')
                    task.task_type = extra_data.get('task_type')
            
            return task
        except Exception as e:
            logger.error(f"Error extracting task fields: {e}")
            return None
    
    @staticmethod
    def estimate_difficulty(task: BenchmarkTask) -> str:
        """Estimate difficulty level based on task content."""
        # Simple heuristics for difficulty estimation
        gold_answer = task.gold_answer
        
        # Check difficulty guess from gold answer
        if 'difficulty_guess' in gold_answer:
            difficulty_value = gold_answer['difficulty_guess']
            if isinstance(difficulty_value, int):
                if difficulty_value <= 15:
                    return "easy"
                elif difficulty_value <= 20:
                    return "moderate"
                elif difficulty_value <= 25:
                    return "challenging"
                else:
                    return "hard"
        
        # Check for complexity indicators
        complexity_score = 0
        
        # Multiple characters increase complexity
        if len(task.characters) > 1:
            complexity_score += 1
        
        # Ritual checks are typically more complex
        if 'ritual' in task.domain.subdomain.lower():
            complexity_score += 1
        
        # Multiple outcome tiers indicate complexity
        if 'outcome_explanation' in gold_answer:
            outcomes = gold_answer['outcome_explanation']
            if isinstance(outcomes, dict) and len(outcomes) >= 6:
                complexity_score += 1
        
        # Map complexity to difficulty
        if complexity_score == 0:
            return "easy"
        elif complexity_score == 1:
            return "moderate"
        elif complexity_score == 2:
            return "challenging"
        else:
            return "hard"


class DatasetLoader:
    """Loader for the Aeonisk YAGS normalized dataset."""
    
    def __init__(self, dataset_path: str):
        """Initialize the dataset loader."""
        self.dataset_path = Path(dataset_path)
        self.tasks: List[BenchmarkTask] = []
        self.parser = TaskParser()
        
    def load_dataset(self) -> List[BenchmarkTask]:
        """Load the complete dataset."""
        logger.info(f"Loading dataset from {self.dataset_path}")
        
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Dataset file not found: {self.dataset_path}")
        
        # Determine file type and load accordingly
        if self.dataset_path.suffix.lower() == '.yaml':
            return self.load_yaml_dataset()
        elif self.dataset_path.suffix.lower() == '.txt':
            return self.load_text_dataset()
        elif self.dataset_path.suffix.lower() == '.json':
            return self.load_json_dataset()
        else:
            # Try to detect format from content
            return self.load_auto_detect()
    
    def load_yaml_dataset(self) -> List[BenchmarkTask]:
        """Load dataset from YAML file."""
        try:
            with open(self.dataset_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if isinstance(data, list):
                # List of tasks
                for item in data:
                    task = self.parser.extract_task_fields(item)
                    if task:
                        task.difficulty_level = self.parser.estimate_difficulty(task)
                        self.tasks.append(task)
            elif isinstance(data, dict):
                # Single task
                task = self.parser.extract_task_fields(data)
                if task:
                    task.difficulty_level = self.parser.estimate_difficulty(task)
                    self.tasks.append(task)
            
            logger.info(f"Loaded {len(self.tasks)} tasks from YAML dataset")
            return self.tasks
        except Exception as e:
            logger.error(f"Error loading YAML dataset: {e}")
            return []
    
    def load_text_dataset(self) -> List[BenchmarkTask]:
        """Load dataset from text file with YAML entries separated by ---."""
        try:
            with open(self.dataset_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Split by --- markers
            entries = re.split(r'^---\s*$', content, flags=re.MULTILINE)
            
            # Skip the first entry if it's just a header comment
            if entries and entries[0].strip().startswith('#'):
                entries = entries[1:]
            
            for entry_text in entries:
                entry_text = entry_text.strip()
                if not entry_text:
                    continue
                
                data = self.parser.parse_yaml_entry(entry_text)
                if data:
                    task = self.parser.extract_task_fields(data)
                    if task:
                        task.difficulty_level = self.parser.estimate_difficulty(task)
                        self.tasks.append(task)
            
            logger.info(f"Loaded {len(self.tasks)} tasks from text dataset")
            return self.tasks
        except Exception as e:
            logger.error(f"Error loading text dataset: {e}")
            return []
    
    def load_json_dataset(self) -> List[BenchmarkTask]:
        """Load dataset from JSON file."""
        try:
            with open(self.dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, list):
                # List of tasks
                for item in data:
                    task = self.parser.extract_task_fields(item)
                    if task:
                        task.difficulty_level = self.parser.estimate_difficulty(task)
                        self.tasks.append(task)
            elif isinstance(data, dict):
                # Single task
                task = self.parser.extract_task_fields(data)
                if task:
                    task.difficulty_level = self.parser.estimate_difficulty(task)
                    self.tasks.append(task)
            
            logger.info(f"Loaded {len(self.tasks)} tasks from JSON dataset")
            return self.tasks
        except Exception as e:
            logger.error(f"Error loading JSON dataset: {e}")
            return []
    
    def load_auto_detect(self) -> List[BenchmarkTask]:
        """Auto-detect file format and load accordingly."""
        try:
            with open(self.dataset_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                f.seek(0)
                content = f.read()
            
            # Try to detect format
            if first_line.startswith('{') or first_line.startswith('['):
                # Likely JSON
                data = json.loads(content)
                return self.load_from_data(data)
            elif '---' in content:
                # Likely YAML with separators
                return self.load_text_dataset()
            else:
                # Try YAML
                data = yaml.safe_load(content)
                return self.load_from_data(data)
        except Exception as e:
            logger.error(f"Error auto-detecting dataset format: {e}")
            return []
    
    def load_from_data(self, data: Any) -> List[BenchmarkTask]:
        """Load tasks from already parsed data."""
        tasks = []
        
        if isinstance(data, list):
            for item in data:
                task = self.parser.extract_task_fields(item)
                if task:
                    task.difficulty_level = self.parser.estimate_difficulty(task)
                    tasks.append(task)
        elif isinstance(data, dict):
            task = self.parser.extract_task_fields(data)
            if task:
                task.difficulty_level = self.parser.estimate_difficulty(task)
                tasks.append(task)
        
        logger.info(f"Loaded {len(tasks)} tasks from parsed data")
        return tasks
    
    def filter_tasks(self, 
                    domains: Optional[List[str]] = None,
                    difficulty_levels: Optional[List[str]] = None,
                    task_types: Optional[List[str]] = None,
                    sample_size: Optional[int] = None,
                    random_seed: Optional[int] = None,
                    filter_task_ids: Optional[List[str]] = None) -> List[BenchmarkTask]:
        """Filter tasks based on criteria."""
        import random
        
        filtered_tasks = self.tasks.copy()
        
        # Filter by task IDs
        if filter_task_ids:
            filtered_tasks = [task for task in filtered_tasks if task.task_id in filter_task_ids]
        
        # Filter by domains
        if domains:
            filtered_tasks = [
                task for task in filtered_tasks 
                if task.domain.core in domains or task.domain.subdomain in domains
            ]
        
        # Filter by difficulty levels
        if difficulty_levels:
            filtered_tasks = [
                task for task in filtered_tasks
                if task.difficulty_level in difficulty_levels
            ]
        
        # Filter by task types
        if task_types:
            filtered_tasks = [
                task for task in filtered_tasks
                if task.task_type in task_types
            ]
        
        # Sample if requested
        if sample_size and sample_size < len(filtered_tasks):
            if random_seed:
                random.seed(random_seed)
            filtered_tasks = random.sample(filtered_tasks, sample_size)
        
        logger.info(f"Filtered to {len(filtered_tasks)} tasks")
        return filtered_tasks
    
    def get_task_statistics(self) -> Dict[str, Any]:
        """Get statistics about the loaded tasks."""
        if not self.tasks:
            return {}
        
        stats = {
            'total_tasks': len(self.tasks),
            'domains': {},
            'difficulty_levels': {},
            'task_types': {}
        }
        
        # Count by domain
        for task in self.tasks:
            domain_key = f"{task.domain.core}.{task.domain.subdomain}"
            stats['domains'][domain_key] = stats['domains'].get(domain_key, 0) + 1
        
        # Count by difficulty level
        for task in self.tasks:
            if task.difficulty_level:
                level = task.difficulty_level
                stats['difficulty_levels'][level] = stats['difficulty_levels'].get(level, 0) + 1
        
        # Count by task type
        for task in self.tasks:
            if task.task_type:
                task_type = task.task_type
                stats['task_types'][task_type] = stats['task_types'].get(task_type, 0) + 1
        
        return stats
    
    def get_task_by_id(self, task_id: str) -> Optional[BenchmarkTask]:
        """Get a specific task by ID."""
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        return None
    
    def get_tasks_by_domain(self, domain: str) -> List[BenchmarkTask]:
        """Get tasks by domain."""
        return [
            task for task in self.tasks
            if task.domain.core == domain or task.domain.subdomain == domain
        ]