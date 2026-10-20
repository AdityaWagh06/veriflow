#!/usr/bin/env python3
"""
Veriflow OpenAPI Contract & Schema Validator.

Validates API request parameters, request bodies, response status codes,
Content-Type headers, and response payloads against OpenAPI 3.0/3.1 schemas:
- Primitive data types (string, integer, number, boolean, null)
- Required object properties and unexpected additional properties
- Array items, minItems, maxItems constraints
- Numeric minimum, maximum, and string minLength, maxLength constraints
- Enum constraints and nullable/union type assertions
- Strict status code and Content-Type matching
- Zero third-party dependencies (built with Python standard library)
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from skills.veriflow.scripts.openapi_loader import OpenApiOperation, OpenApiSpec


@dataclass
class SchemaValidationError:
    """Represents a specific contract violation during schema or response validation."""

    path: str
    message: str
    error_type: str
    expected: Any = None
    actual: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "message": self.message,
            "error_type": self.error_type,
            "expected": self.expected,
            "actual": self.actual,
        }


def validate_schema(
    instance: Any,
    schema: Dict[str, Any],
    path: str = "$",
    spec: Optional[OpenApiSpec] = None,
    visited_refs: Optional[Set[str]] = None,
) -> List[SchemaValidationError]:
    """
    Validate a data instance (JSON scalar, list, or dict) against an OpenAPI schema.
    Returns a list of SchemaValidationError instances.
    """
    errors: List[SchemaValidationError] = []

    if not isinstance(schema, dict):
        return errors

    if visited_refs is None:
        visited_refs = set()

    # Resolve $ref if present
    if "$ref" in schema and spec is not None:
        ref_target = schema["$ref"]
        if ref_target in visited_refs:
            return errors  # Circular reference broken
        resolved = spec.resolve_schema(schema, visited=visited_refs)
        new_visited = visited_refs | {ref_target}
        return validate_schema(instance, resolved, path=path, spec=spec, visited_refs=new_visited)

    # Check nullable / null handling
    is_nullable = schema.get("nullable", False)
    schema_type = schema.get("type")

    # In OpenAPI 3.1, type can be an array, e.g. ["string", "null"]
    if isinstance(schema_type, list):
        if instance is None and "null" in schema_type:
            return errors
        # If instance is not null, try matching any of the declared types
        if instance is None and "null" not in schema_type:
            errors.append(
                SchemaValidationError(
                    path=path,
                    message=f"Value at {path} is null, but null is not an allowed type ({schema_type})",
                    error_type="NULL_NOT_ALLOWED",
                    expected=schema_type,
                    actual="null",
                )
            )
            return errors
    else:
        if instance is None:
            if is_nullable:
                return errors
            if schema_type:
                errors.append(
                    SchemaValidationError(
                        path=path,
                        message=f"Value at {path} is null, but field is not nullable (expected {schema_type})",
                        error_type="NULL_NOT_ALLOWED",
                        expected=schema_type,
                        actual="null",
                    )
                )
            return errors

    # Enum validation
    if "enum" in schema and isinstance(schema["enum"], list):
        if instance not in schema["enum"]:
            errors.append(
                SchemaValidationError(
                    path=path,
                    message=f"Value '{instance}' at {path} is not one of allowed enum values: {schema['enum']}",
                    error_type="ENUM_VIOLATION",
                    expected=schema["enum"],
                    actual=instance,
                )
            )

    # Type validation
    if schema_type:
        expected_types = schema_type if isinstance(schema_type, list) else [schema_type]
        valid_type = False

        for t in expected_types:
            if t == "string" and isinstance(instance, str):
                valid_type = True
                _validate_string_constraints(instance, schema, path, errors)
                break
            elif t == "integer" and isinstance(instance, int) and not isinstance(instance, bool):
                valid_type = True
                _validate_numeric_constraints(instance, schema, path, errors)
                break
            elif t == "number" and isinstance(instance, (int, float)) and not isinstance(instance, bool):
                valid_type = True
                _validate_numeric_constraints(instance, schema, path, errors)
                break
            elif t == "boolean" and isinstance(instance, bool):
                valid_type = True
                break
            elif t == "array" and isinstance(instance, list):
                valid_type = True
                _validate_array_constraints(instance, schema, path, errors, spec, visited_refs)
                break
            elif t == "object" and isinstance(instance, dict):
                valid_type = True
                _validate_object_constraints(instance, schema, path, errors, spec, visited_refs)
                break

        if not valid_type:
            errors.append(
                SchemaValidationError(
                    path=path,
                    message=f"Type mismatch at {path}: expected {schema_type}, got {type(instance).__name__}",
                    error_type="TYPE_MISMATCH",
                    expected=schema_type,
                    actual=type(instance).__name__,
                )
            )
    else:
        # If type not explicitly specified, inspect properties/items presence
        if "properties" in schema and isinstance(instance, dict):
            _validate_object_constraints(instance, schema, path, errors, spec, visited_refs)
        elif "items" in schema and isinstance(instance, list):
            _validate_array_constraints(instance, schema, path, errors, spec, visited_refs)

    return errors


def _validate_string_constraints(
    instance: str,
    schema: Dict[str, Any],
    path: str,
    errors: List[SchemaValidationError],
) -> None:
    """Validate string length and pattern."""
    if "minLength" in schema and len(instance) < schema["minLength"]:
        errors.append(
            SchemaValidationError(
                path=path,
                message=f"String at {path} length {len(instance)} is shorter than minLength {schema['minLength']}",
                error_type="CONSTRAINT_VIOLATION",
                expected=f">= {schema['minLength']}",
                actual=len(instance),
            )
        )

    if "maxLength" in schema and len(instance) > schema["maxLength"]:
        errors.append(
            SchemaValidationError(
                path=path,
                message=f"String at {path} length {len(instance)} is longer than maxLength {schema['maxLength']}",
                error_type="CONSTRAINT_VIOLATION",
                expected=f"<= {schema['maxLength']}",
                actual=len(instance),
            )
        )

    if "pattern" in schema:
        pattern_str = schema["pattern"]
        try:
            if not re.search(pattern_str, instance):
                errors.append(
                    SchemaValidationError(
                        path=path,
                        message=f"String at {path} does not match pattern '{pattern_str}'",
                        error_type="CONSTRAINT_VIOLATION",
                        expected=pattern_str,
                        actual=instance,
                    )
                )
        except re.error:
            pass


def _validate_numeric_constraints(
    instance: Union[int, float],
    schema: Dict[str, Any],
    path: str,
    errors: List[SchemaValidationError],
) -> None:
    """Validate minimum, maximum, and exclusive boundaries."""
    if "minimum" in schema:
        min_val = schema["minimum"]
        is_exclusive = schema.get("exclusiveMinimum", False)
        if isinstance(is_exclusive, bool):
            violation = instance <= min_val if is_exclusive else instance < min_val
            op = ">" if is_exclusive else ">="
        else:
            violation = instance <= is_exclusive
            op = f"> {is_exclusive}"
        if violation:
            errors.append(
                SchemaValidationError(
                    path=path,
                    message=f"Numeric value {instance} at {path} violates minimum constraint ({op} {min_val})",
                    error_type="CONSTRAINT_VIOLATION",
                    expected=f"{op} {min_val}",
                    actual=instance,
                )
            )

    if "maximum" in schema:
        max_val = schema["maximum"]
        is_exclusive = schema.get("exclusiveMaximum", False)
        if isinstance(is_exclusive, bool):
            violation = instance >= max_val if is_exclusive else instance > max_val
            op = "<" if is_exclusive else "<="
        else:
            violation = instance >= is_exclusive
            op = f"< {is_exclusive}"
        if violation:
            errors.append(
                SchemaValidationError(
                    path=path,
                    message=f"Numeric value {instance} at {path} violates maximum constraint ({op} {max_val})",
                    error_type="CONSTRAINT_VIOLATION",
                    expected=f"{op} {max_val}",
                    actual=instance,
                )
            )


def _validate_array_constraints(
    instance: List[Any],
    schema: Dict[str, Any],
    path: str,
    errors: List[SchemaValidationError],
    spec: Optional[OpenApiSpec],
    visited_refs: Set[str],
) -> None:
    """Validate array length and item schemas."""
    if "minItems" in schema and len(instance) < schema["minItems"]:
        errors.append(
            SchemaValidationError(
                path=path,
                message=f"Array at {path} has {len(instance)} items; expected at least {schema['minItems']}",
                error_type="CONSTRAINT_VIOLATION",
                expected=f">= {schema['minItems']}",
                actual=len(instance),
            )
        )

    if "maxItems" in schema and len(instance) > schema["maxItems"]:
        errors.append(
            SchemaValidationError(
                path=path,
                message=f"Array at {path} has {len(instance)} items; expected at most {schema['maxItems']}",
                error_type="CONSTRAINT_VIOLATION",
                expected=f"<= {schema['maxItems']}",
                actual=len(instance),
            )
        )

    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        for idx, item in enumerate(instance):
            item_errors = validate_schema(
                item,
                item_schema,
                path=f"{path}[{idx}]",
                spec=spec,
                visited_refs=set(visited_refs),
            )
            errors.extend(item_errors)


def _validate_object_constraints(
    instance: Dict[str, Any],
    schema: Dict[str, Any],
    path: str,
    errors: List[SchemaValidationError],
    spec: Optional[OpenApiSpec],
    visited_refs: Set[str],
) -> None:
    """Validate required object properties, property schemas, and unexpected additionalProperties."""
    required_fields = schema.get("required", [])
    if isinstance(required_fields, list):
        for req in required_fields:
            if req not in instance:
                errors.append(
                    SchemaValidationError(
                        path=f"{path}.{req}",
                        message=f"Missing required property '{req}' at {path}",
                        error_type="MISSING_REQUIRED_FIELD",
                        expected=f"Property '{req}' present",
                        actual="Missing",
                    )
                )

    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        for prop_name, prop_val in instance.items():
            if prop_name in properties:
                prop_schema = properties[prop_name]
                if isinstance(prop_schema, dict):
                    prop_errors = validate_schema(
                        prop_val,
                        prop_schema,
                        path=f"{path}.{prop_name}",
                        spec=spec,
                        visited_refs=set(visited_refs),
                    )
                    errors.extend(prop_errors)

    # additionalProperties
    add_props = schema.get("additionalProperties")
    if add_props is False:
        allowed_props = set(properties.keys()) if isinstance(properties, dict) else set()
        for prop_name in instance.keys():
            if prop_name not in allowed_props:
                errors.append(
                    SchemaValidationError(
                        path=f"{path}.{prop_name}",
                        message=f"Unexpected additional property '{prop_name}' at {path}",
                        error_type="ADDITIONAL_PROPERTY",
                        expected=f"Allowed properties: {sorted(list(allowed_props))}",
                        actual=prop_name,
                    )
                )


def validate_api_response(
    operation: OpenApiOperation,
    status_code: int,
    headers: Dict[str, str],
    body_data: Any,
    spec: Optional[OpenApiSpec] = None,
) -> List[SchemaValidationError]:
    """
    Validate a live HTTP response against an operation's documented OpenAPI responses.
    Checks:
    1. Status code is documented (or falls under default)
    2. Response Content-Type matches documented media types
    3. Response body adheres to documented schema
    """
    errors: List[SchemaValidationError] = []
    status_str = str(status_code)

    responses = operation.responses
    doc_response = responses.get(status_str) or responses.get("default")

    if not doc_response:
        documented_statuses = sorted(list(responses.keys()))
        errors.append(
            SchemaValidationError(
                path=f"responses.{status_str}",
                message=(
                    f"Undocumented status code {status_code} returned for {operation.method} {operation.path}. "
                    f"Documented response status codes: {documented_statuses}"
                ),
                error_type="UNEXPECTED_STATUS_CODE",
                expected=documented_statuses,
                actual=status_code,
            )
        )
        return errors

    content_map = doc_response.get("content", {})
    if not content_map:
        # No body schema documented (e.g. 204 No Content)
        return errors

    # Check Content-Type header
    raw_content_type = ""
    for k, v in headers.items():
        if k.lower() == "content-type":
            raw_content_type = v
            break

    matched_media_type = None
    normalized_content_type = raw_content_type.split(";")[0].strip().lower()

    for media_pattern in content_map.keys():
        if media_pattern.lower() == normalized_content_type:
            matched_media_type = media_pattern
            break
        # Support wildcards like application/* or */*
        if media_pattern == "*/*" or (
            media_pattern.endswith("/*") and normalized_content_type.startswith(media_pattern[:-1])
        ):
            matched_media_type = media_pattern
            break

    if not matched_media_type:
        documented_types = sorted(list(content_map.keys()))
        errors.append(
            SchemaValidationError(
                path=f"responses.{status_str}.content",
                message=(
                    f"Response Content-Type '{raw_content_type}' does not match documented media types for "
                    f"{operation.method} {operation.path} (status {status_code}). Documented: {documented_types}"
                ),
                error_type="UNEXPECTED_CONTENT_TYPE",
                expected=documented_types,
                actual=raw_content_type,
            )
        )
        return errors

    # Validate response body against media type schema
    media_obj = content_map[matched_media_type]
    schema = media_obj.get("schema")
    if schema and isinstance(schema, dict):
        body_errors = validate_schema(body_data, schema, path="$", spec=spec)
        errors.extend(body_errors)

    return errors
