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

            # If field has default_factory, replace with actual default value
            if hasattr(field_info, 'default_factory') and field_info.default_factory and not field_info.is_required():
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
            elif not field_info.is_required():
                # Optional field with existing default
                new_defaults[field_name] = field_info
            # If field is required, don't add to defaults dict

        # Create new model dynamically
        new_model = type(
            model.__name__,
            (BaseModel,),
            {
                '__annotations__': new_annotations,
                **new_defaults,
                '__doc__': model.__doc__,
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

    # Use OpenAI's native structured output API
    # NOTE: This runs in a thread pool to avoid blocking the event loop
    # NOTE: gpt-5-mini and newer models use max_completion_tokens instead of max_tokens
    # NOTE: OpenAI requires strict schema validation - Pydantic models work but need proper config
    try:
        completion = await asyncio.to_thread(
            client.beta.chat.completions.parse,
            model=model,
            messages=messages,
            max_completion_tokens=max_tokens,  # gpt-5-mini requires this parameter name
            temperature=temperature,
            response_format=compatible_model,  # Use compatible model instead of original
            **kwargs
        )
    except Exception as e:
        # If schema validation fails, provide helpful error message
        error_msg = str(e)
        if "required" in error_msg and "properties" in error_msg:
            logger.error(
                f"❌ OpenAI schema validation failed. This likely means the Pydantic model "
                f"has optional fields that aren't properly configured for OpenAI's strict mode.\n"
                f"Error: {error_msg}\n"
                f"Model: {result_type.__name__}"
            )
        raise

    # Extract parsed output (already validated Pydantic model)
    compatible_output = completion.choices[0].message.parsed

    # Convert back to original type
    # We use model_dump() then parse the dict with the original type
    # This ensures the return type matches what was requested
    output_dict = compatible_output.model_dump()
    output = result_type.model_validate(output_dict)

    # Log token usage
    if hasattr(completion, 'usage') and completion.usage:
        logger.info(
            f"📊 OpenAI tokens: {completion.usage.prompt_tokens} input + "
            f"{completion.usage.completion_tokens} output = {completion.usage.total_tokens} total"
        )

    return output
