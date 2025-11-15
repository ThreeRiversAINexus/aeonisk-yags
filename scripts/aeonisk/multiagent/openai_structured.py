"""
OpenAI-specific structured output implementation.

This module provides a dedicated implementation for OpenAI's native Structured Output API,
bypassing Pydantic AI to avoid message formatting incompatibilities.

TODO: Remove this module once Pydantic AI fixes the null content bug with OpenAI.
      See: https://github.com/anthropics/pydantic-ai/issues/XXX
"""

import asyncio
import logging
from typing import Type, Optional, TypeVar
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


def _create_openai_compatible_model(pydantic_model: Type[T]) -> Type[T]:
    """
    Create an OpenAI-compatible version of a Pydantic model.

    OpenAI's structured output has stricter requirements than standard Pydantic:
    1. All fields NOT in 'required' must have explicit defaults (not default_factory)
    2. default_factory fields don't generate "default" in JSON schema
    3. This applies RECURSIVELY to all nested models

    Solution: Recursively create new models with default_factory replaced by actual defaults.
    """
    from pydantic import Field, create_model
    from pydantic.fields import FieldInfo
    import copy
    from typing import get_origin, get_args

    # Cache to avoid infinite recursion on circular references
    _model_cache = {}

    def _fix_model_recursive(model: Type[BaseModel]) -> Type[BaseModel]:
        # Check cache first
        if model in _model_cache:
            return _model_cache[model]

        # Get all fields from original model
        model_fields = model.model_fields
        new_annotations = {}
        new_defaults = {}

        for field_name, field_info in model_fields.items():
            # Get the annotation (might be a nested Pydantic model)
            annotation = field_info.annotation

            # Check if annotation is a Pydantic model or contains one
            fixed_annotation = annotation
            origin = get_origin(annotation)

            # Handle Optional[Model], List[Model], etc.
            if origin is not None:
                args = get_args(annotation)
                fixed_args = []
                for arg in args:
                    if isinstance(arg, type) and issubclass(arg, BaseModel):
                        # Recursively fix nested model
                        fixed_args.append(_fix_model_recursive(arg))
                    else:
                        fixed_args.append(arg)
                # Reconstruct the generic type with fixed args
                if fixed_args != list(args):
                    fixed_annotation = origin[tuple(fixed_args)]
            elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
                # Direct Pydantic model field - fix it recursively
                fixed_annotation = _fix_model_recursive(annotation)

            new_annotations[field_name] = fixed_annotation

            # Handle required vs optional fields
            if field_info.is_required():
                # Required field - don't add to defaults dict (only in annotations)
                pass
            elif hasattr(field_info, 'default_factory') and field_info.default_factory:
                # Optional field with default_factory - convert to explicit default
                try:
                    # Call default_factory once to get the default value
                    default_value = field_info.default_factory()

                    # Create new Field with actual default instead of factory
                    new_field = Field(
                        default=default_value,
                        description=field_info.description,
                        title=field_info.title,
                    )
                    new_defaults[field_name] = new_field
                    logger.debug(f"Converted default_factory for {model.__name__}.{field_name} to default: {default_value}")
                except Exception as e:
                    logger.warning(f"Could not convert default_factory for {model.__name__}.{field_name}: {e}")
                    # Keep original field
                    new_defaults[field_name] = field_info
            elif field_info.default is not None or hasattr(field_info, 'default'):
                # Optional field with existing default value
                new_defaults[field_name] = field_info
            else:
                # Optional field WITHOUT any default - OpenAI strict mode requires a default
                # Use None as the default for Optional fields
                logger.warning(f"Field {model.__name__}.{field_name} is optional but has no default, adding default=None for OpenAI strict mode")
                new_field = Field(
                    default=None,
                    description=field_info.description,
                    title=field_info.title,
                )
                new_defaults[field_name] = new_field

        # Create new model dynamically with UNIQUE name to avoid Pydantic schema caching
        # Use id() to ensure the name is unique
        unique_name = f"{model.__name__}_OpenAICompat_{id(model)}"

        # Create model with ConfigDict to set additionalProperties=false for OpenAI strict mode
        from pydantic import ConfigDict

        new_model = type(
            unique_name,
            (BaseModel,),
            {
                '__annotations__': new_annotations,
                **new_defaults,
                '__doc__': model.__doc__,
                '__module__': model.__module__,  # Preserve module for proper schema generation
                'model_config': ConfigDict(extra='forbid'),  # This sets additionalProperties=false
            }
        )

        # Cache it
        _model_cache[model] = new_model
        return new_model

    return _fix_model_recursive(pydantic_model)


async def generate_structured_openai_native(
    client,  # openai.OpenAI client
    model: str,
    prompt: str,
    result_type: Type[T],
    system_prompt: Optional[str] = None,
    max_tokens: int = 5000,
    temperature: float = 1.0,
    llm_logger=None,  # LLMLogger instance for JSONL logging
    agent_prompt_logger=None,  # AgentPromptLogger for human-readable logs
    agent_id: Optional[str] = None,
    current_round: Optional[int] = None,
    call_sequence: int = 0,
    **kwargs
) -> T:
    """
    Generate structured output using OpenAI's native beta.chat.completions.parse() API.

    This bypasses Pydantic AI entirely to avoid the null content message bug
    that occurs when using Pydantic AI with OpenAI's structured output mode.

    Args:
        client: OpenAI client instance
        model: Model name (e.g., "gpt-5-mini")
        prompt: User prompt/input text
        result_type: Pydantic model class defining the output schema
        system_prompt: Optional system instructions
        max_tokens: Maximum tokens for generation (default: 5000)
        temperature: Sampling temperature (MUST be 1.0 for structured output)
        **kwargs: Additional model-specific parameters

    Returns:
        Validated instance of result_type

    Raises:
        Exception: If generation or validation fails

    Example:
        ```python
        from openai import OpenAI
        from schemas.action_resolution import ActionResolution

        client = OpenAI(api_key="...")
        resolution = await generate_structured_openai_native(
            client=client,
            model="gpt-5-mini",
            prompt="You shoot the bandit for 12 damage",
            result_type=ActionResolution,
            system_prompt="You are a dungeon master",
            temperature=1.0
        )
        print(resolution.narration)
        ```
    """
    # OpenAI structured output REQUIRES temperature=1.0
    if temperature != 1.0:
        logger.warning(f"OpenAI structured output requires temperature=1.0, overriding {temperature}")
        temperature = 1.0

    # Build messages array
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # Create OpenAI-compatible version of the Pydantic model
    # This fixes default_factory fields that don't generate "default" in JSON schema
    compatible_model = _create_openai_compatible_model(result_type)

    # Debug: Log the schema being sent to OpenAI
    if logger.isEnabledFor(logging.DEBUG):
        import json
        schema = compatible_model.model_json_schema()
        logger.debug(f"OpenAI schema for {result_type.__name__}: {len(str(schema))} chars")

        # Check for problematic patterns
        if '$defs' in schema:
            for def_name, def_schema in schema['$defs'].items():
                required = set(def_schema.get('required', []))
                properties = set(def_schema['properties'].keys()) if 'properties' in def_schema else set()
                optional = properties - required
                missing_defaults = []
                for field in optional:
                    if 'default' not in def_schema['properties'][field]:
                        missing_defaults.append(field)
                if missing_defaults:
                    logger.warning(f"  {def_name} has optional fields WITHOUT defaults: {missing_defaults}")

        # Specifically check PurchaseEffect
        if '$defs' in schema and 'PurchaseEffect_OpenAICompat' in [k for k in schema['$defs'].keys() if 'PurchaseEffect' in k]:
            for def_name in schema['$defs'].keys():
                if 'PurchaseEffect' in def_name:
                    pe_schema = schema['$defs'][def_name]
                    logger.debug(f"  {def_name} required: {pe_schema.get('required', [])}")
                    if 'currency_spent' in pe_schema.get('properties', {}):
                        cs = pe_schema['properties']['currency_spent']
                        logger.debug(f"  currency_spent has default: {'default' in cs}")

    # Use OpenAI's chat completions API with JSON schema mode
    # NOTE: This runs in a thread pool to avoid blocking the event loop
    # NOTE: gpt-5-mini and newer models use max_completion_tokens instead of max_tokens
    # NOTE: Using regular API instead of beta.parse() due to OpenAI API bugs with nested schemas
    try:
        # Get the JSON schema
        json_schema = compatible_model.model_json_schema()

        # Use the regular API with json_schema mode
        completion = await asyncio.to_thread(
            client.chat.completions.create,
            model=model,
            messages=messages,
            max_completion_tokens=max_tokens,  # gpt-5-mini requires this parameter name
            temperature=temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": compatible_model.__name__,
                    "schema": json_schema,
                    "strict": False  # Disable strict mode - OpenAI's strict validation is too restrictive
                }
            },
            **kwargs
        )
    except Exception as e:
        # If schema validation fails, provide helpful error message
        error_msg = str(e)
        if "required" in error_msg and "properties" in error_msg:
            # Dump schema to temp file for debugging
            import tempfile
            json_schema = compatible_model.model_json_schema()
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, prefix='openai_schema_') as f:
                import json
                json.dump(json_schema, f, indent=2)
                logger.error(
                    f"❌ OpenAI schema validation failed. This likely means the Pydantic model "
                    f"has optional fields that aren't properly configured for OpenAI's strict mode.\n"
                    f"Error: {error_msg}\n"
                    f"Model: {result_type.__name__}\n"
                    f"Schema dumped to: {f.name}"
                )
        raise

    # Extract JSON content from response
    content = completion.choices[0].message.content

    # Check for empty/null content
    if not content:
        raise ValueError(
            f"OpenAI returned empty content for {result_type.__name__}. "
            f"This may indicate the model refused to generate output or hit a filter. "
            f"Check the completion object for refusal/filter flags."
        )

    # Parse the JSON and validate with Pydantic
    import json
    output_dict = json.loads(content)

    # Validate with the original type (not the compatible wrapper)
    output = result_type.model_validate(output_dict)

    # Extract token usage
    tokens = {}
    if hasattr(completion, 'usage') and completion.usage:
        tokens = {
            'input': completion.usage.prompt_tokens,
            'output': completion.usage.completion_tokens,
            'total': completion.usage.total_tokens
        }
        logger.info(
            f"📊 OpenAI tokens: {tokens['input']} input + "
            f"{tokens['output']} output = {tokens['total']} total"
        )

    # Log to JSONL for replay/ML training
    if llm_logger:
        try:
            llm_logger._log_llm_call(
                messages=messages,
                response=content,
                model=model,
                temperature=temperature,
                tokens=tokens,
                current_round=current_round,
                call_sequence=call_sequence
            )
        except Exception as e:
            logger.warning(f"Failed to log LLM call to JSONL: {e}")

    # Log to human-readable agent prompt log
    if agent_prompt_logger and agent_id:
        try:
            # Combine system + user prompt for readability
            full_prompt = ""
            if system_prompt:
                full_prompt = f"System: {system_prompt}\n\nUser: {prompt}"
            else:
                full_prompt = f"User: {prompt}"

            agent_prompt_logger.log_llm_call(
                agent_id=agent_id,
                round_num=current_round,
                call_sequence=call_sequence,
                prompt=full_prompt,
                response=content,
                model=model,
                source="openai_structured"
            )
        except Exception as e:
            logger.warning(f"Failed to log to agent prompt logger: {e}")

    return output
