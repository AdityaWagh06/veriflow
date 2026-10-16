#!/usr/bin/env python3
"""
Veriflow OpenAPI Specification Loader & Safe Reference Resolver.

Supports OpenAPI 3.0.x and 3.1.x in JSON and YAML formats:
- Validates specification version, top-level required fields, and path operations.
- Resolves local JSON Pointer references (`#/components/schemas/...`).
- Detects circular references safely without infinite recursion.
- Enforces strict path-traversal prevention on relative file references.
- Blocks arbitrary remote `$ref` URL fetching for security.
- Standard library JSON parsing; optional PyYAML for YAML with clear BLOCKED diagnostics if absent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union


class OpenApiSpecError(ValueError):
    """Raised when an OpenAPI document is malformed, unsupported, or violates safety boundaries."""
    pass


class OpenApiBlockedError(OpenApiSpecError):
    """Raised when a specification requires an unavailable dependency (e.g. PyYAML for YAML)."""
    pass


@dataclass
class OpenApiOperation:
    """Represents a single documented HTTP operation on an API path."""

    path: str
    method: str
    operation_id: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    request_body: Optional[Dict[str, Any]] = None
    responses: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    security: Optional[List[Dict[str, List[str]]]] = None
    deprecated: bool = False


class OpenApiSpec:
    """Parsed and validated OpenAPI 3.0 / 3.1 specification."""

    SUPPORTED_PREFIXES = ("3.0.", "3.1.")

    def __init__(
        self,
        raw_data: Dict[str, Any],
        file_path: Optional[Path] = None,
        base_dir: Optional[Path] = None,
    ) -> None:
        self.raw_data = raw_data
        self.file_path = file_path
        self.base_dir = (base_dir or (file_path.parent if file_path else Path.cwd())).resolve()
        self.unsupported_features: List[str] = []

        self._validate_top_level()
        self.version: str = str(self.raw_data["openapi"]).strip()
        self.info: Dict[str, Any] = self.raw_data["info"]
        self.title: str = self.info.get("title", "")
        self.api_version: str = str(self.info.get("version", ""))
        self.servers: List[Dict[str, Any]] = self.raw_data.get("servers", [])
        self.paths: Dict[str, Any] = self.raw_data.get("paths", {})
        self.components: Dict[str, Any] = self.raw_data.get("components", {})

    def _validate_top_level(self) -> None:
        """Validate required top-level OpenAPI keys and versions."""
        if not isinstance(self.raw_data, dict):
            raise OpenApiSpecError("OpenAPI specification root must be a JSON/YAML object (dictionary).")

        if "openapi" not in self.raw_data:
            if "swagger" in self.raw_data:
                swagger_ver = self.raw_data.get("swagger")
                raise OpenApiSpecError(
                    f"Unsupported legacy Swagger/OpenAPI version '{swagger_ver}'. "
                    "Veriflow Phase 4 requires OpenAPI 3.0.x or 3.1.x."
                )
            raise OpenApiSpecError("Missing required top-level field: 'openapi'")

        version_str = str(self.raw_data["openapi"]).strip()
        if not any(version_str.startswith(p) for p in self.SUPPORTED_PREFIXES):
            raise OpenApiSpecError(
                f"Unsupported OpenAPI version '{version_str}'. "
                "Supported versions are OpenAPI 3.0.x and 3.1.x."
            )

        if "info" not in self.raw_data or not isinstance(self.raw_data["info"], dict):
            raise OpenApiSpecError("Missing required top-level object: 'info'")

        info = self.raw_data["info"]
        if "title" not in info or not str(info["title"]).strip():
            raise OpenApiSpecError("Missing required field in info object: 'title'")

        if "version" not in info:
            raise OpenApiSpecError("Missing required field in info object: 'version'")

        if "paths" not in self.raw_data or not isinstance(self.raw_data["paths"], dict):
            raise OpenApiSpecError("Missing required top-level object: 'paths'")

    def resolve_ref(
        self,
        ref: str,
        current_doc: Optional[Dict[str, Any]] = None,
        visited: Optional[Set[str]] = None,
    ) -> Any:
        """
        Safely resolve a JSON pointer reference.
        - Supports local references: `#/components/schemas/Pet`
        - Supports local relative file references: `./common.json#/Pet` (within base_dir)
        - Detects circular references to avoid infinite recursion
        - Rejects remote HTTP/HTTPS references and directory traversal
        """
        if visited is None:
            visited = set()

        if ref in visited:
            # Circular reference detected; return placeholder to terminate recursion
            return {"$ref": ref, "_circular": True}

        visited.add(ref)

        # Check for remote URL reference
        if ref.startswith("http://") or ref.startswith("https://"):
            raise OpenApiSpecError(
                f"Remote reference '{ref}' is blocked by Veriflow safety boundaries. "
                "Specifications must use local references."
            )

        file_part, _, pointer_part = ref.partition("#")

        # Resolve target document
        if file_part:
            target_path = (self.base_dir / file_part).resolve()
            # Path traversal check
            try:
                target_path.relative_to(self.base_dir)
            except ValueError:
                raise OpenApiSpecError(
                    f"Path traversal detected: reference '{ref}' attempts to access files "
                    f"outside specification base directory '{self.base_dir}'."
                )

            if not target_path.is_file():
                raise OpenApiSpecError(f"Referenced file not found: '{file_part}' (resolved to '{target_path}')")

            doc = _parse_file(target_path)
        else:
            doc = current_doc if current_doc is not None else self.raw_data

        if not pointer_part:
            return doc

        # Resolve JSON Pointer
        if not pointer_part.startswith("/"):
            raise OpenApiSpecError(f"Invalid JSON Pointer in reference '{ref}'. Expected leading '/'.")

        tokens = pointer_part.lstrip("/").split("/")
        curr = doc

        for token in tokens:
            # Unescape JSON pointer: ~1 -> /, ~0 -> ~
            key = token.replace("~1", "/").replace("~0", "~")

            if isinstance(curr, dict):
                if key not in curr:
                    raise OpenApiSpecError(f"Unresolved reference '{ref}': property '{key}' not found.")
                curr = curr[key]
            elif isinstance(curr, list):
                try:
                    idx = int(key)
                    curr = curr[idx]
                except (ValueError, IndexError):
                    raise OpenApiSpecError(f"Unresolved reference '{ref}': invalid array index '{key}'.")
            else:
                raise OpenApiSpecError(f"Unresolved reference '{ref}': cannot traverse into scalar at '{key}'.")

        # If the resolved target is another reference, chain resolution
        if isinstance(curr, dict) and "$ref" in curr and isinstance(curr["$ref"], str):
            return self.resolve_ref(curr["$ref"], current_doc=doc, visited=visited)

        return curr

    def resolve_schema(
        self,
        schema: Dict[str, Any],
        visited: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """Deep-resolve any top-level or nested $ref within a schema."""
        if visited is None:
            visited = set()

        if not isinstance(schema, dict):
            return schema

        if "$ref" in schema and isinstance(schema["$ref"], str):
            ref = schema["$ref"]
            if ref in visited:
                return {"$ref": ref, "_circular": True}

            resolved = self.resolve_ref(ref, visited=set(visited))
            if isinstance(resolved, dict):
                merged = dict(resolved)
                for k, v in schema.items():
                    if k != "$ref":
                        merged[k] = v
                return self.resolve_schema(merged, visited=visited | {ref})
            return resolved

        resolved_schema = dict(schema)

        # Recursively resolve properties
        if "properties" in resolved_schema and isinstance(resolved_schema["properties"], dict):
            resolved_props = {}
            for prop_name, prop_schema in resolved_schema["properties"].items():
                resolved_props[prop_name] = self.resolve_schema(prop_schema, visited=set(visited))
            resolved_schema["properties"] = resolved_props

        # Recursively resolve items
        if "items" in resolved_schema and isinstance(resolved_schema["items"], dict):
            resolved_schema["items"] = self.resolve_schema(resolved_schema["items"], visited=set(visited))

        return resolved_schema

    def get_operations(self) -> List[OpenApiOperation]:
        """Extract and return all documented API operations."""
        operations: List[OpenApiOperation] = []
        valid_methods = {"get", "post", "put", "delete", "patch", "options", "head", "trace"}

        for path, path_item in self.paths.items():
            if not isinstance(path_item, dict):
                continue

            # Path-level parameters apply to all operations unless overridden
            path_params = path_item.get("parameters", [])
            if not isinstance(path_params, list):
                path_params = []

            for method_name, op_item in path_item.items():
                method_lower = method_name.lower()
                if method_lower not in valid_methods or not isinstance(op_item, dict):
                    continue

                # Combine path-level and operation-level parameters
                op_params = op_item.get("parameters", [])
                if not isinstance(op_params, list):
                    op_params = []

                merged_params: List[Dict[str, Any]] = []
                seen_param_keys = set()

                for p in op_params:
                    if isinstance(p, dict) and "$ref" in p:
                        p = self.resolve_ref(p["$ref"])
                    if isinstance(p, dict) and "name" in p and "in" in p:
                        key = (p["name"], p["in"])
                        seen_param_keys.add(key)
                        merged_params.append(p)

                for p in path_params:
                    if isinstance(p, dict) and "$ref" in p:
                        p = self.resolve_ref(p["$ref"])
                    if isinstance(p, dict) and "name" in p and "in" in p:
                        key = (p["name"], p["in"])
                        if key not in seen_param_keys:
                            merged_params.append(p)

                # Request body
                req_body = op_item.get("requestBody")
                if isinstance(req_body, dict) and "$ref" in req_body:
                    req_body = self.resolve_ref(req_body["$ref"])

                # Responses
                raw_responses = op_item.get("responses", {})
                resolved_responses: Dict[str, Dict[str, Any]] = {}
                if isinstance(raw_responses, dict):
                    for status_code, resp_item in raw_responses.items():
                        status_str = str(status_code)
                        if isinstance(resp_item, dict) and "$ref" in resp_item:
                            resolved_responses[status_str] = self.resolve_ref(resp_item["$ref"])
                        elif isinstance(resp_item, dict):
                            resolved_responses[status_str] = resp_item

                operations.append(
                    OpenApiOperation(
                        path=path,
                        method=method_lower.upper(),
                        operation_id=op_item.get("operationId"),
                        summary=op_item.get("summary"),
                        description=op_item.get("description"),
                        parameters=merged_params,
                        request_body=req_body if isinstance(req_body, dict) else None,
                        responses=resolved_responses,
                        security=op_item.get("security", self.raw_data.get("security")),
                        deprecated=bool(op_item.get("deprecated", False)),
                    )
                )

        return operations


def _parse_file(file_path: Path) -> Dict[str, Any]:
    """Parse a file as JSON or YAML."""
    text = file_path.read_text(encoding="utf-8", errors="replace")
    suffix = file_path.suffix.lower()

    if suffix == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise OpenApiSpecError(f"Malformed JSON in '{file_path.name}': {exc}")

    if suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ModuleNotFoundError:
            raise OpenApiBlockedError(
                f"YAML specification discovered at '{file_path.name}', but PyYAML is not installed. "
                "Action: Install PyYAML (e.g. 'pip install pyyaml') or convert the specification to JSON."
            )
        try:
            parsed = yaml.safe_load(text)
            if not isinstance(parsed, dict):
                raise OpenApiSpecError(f"YAML in '{file_path.name}' parsed to non-object: {type(parsed).__name__}")
            return parsed
        except Exception as exc:
            if isinstance(exc, OpenApiSpecError):
                raise
            raise OpenApiSpecError(f"Malformed YAML in '{file_path.name}': {exc}")

    # Fallback: try JSON then YAML
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
            parsed = yaml.safe_load(text)
            if isinstance(parsed, dict):
                return parsed
        except ModuleNotFoundError:
            pass
        except Exception:
            pass

    raise OpenApiSpecError(f"Could not parse '{file_path.name}' as valid JSON or YAML OpenAPI specification.")


def load_openapi_spec(
    source: Union[str, Path, Dict[str, Any]],
    base_dir: Optional[Union[str, Path]] = None,
) -> OpenApiSpec:
    """Load, parse, and validate an OpenAPI specification from a file path, raw string, or dictionary."""
    if isinstance(source, dict):
        base_path = Path(base_dir).resolve() if base_dir else Path.cwd().resolve()
        return OpenApiSpec(raw_data=source, base_dir=base_path)

    path_obj = Path(source)
    if path_obj.is_file():
        file_path = path_obj.resolve()
        data = _parse_file(file_path)
        return OpenApiSpec(raw_data=data, file_path=file_path, base_dir=file_path.parent)

    # If it's a raw JSON string
    text = str(source).strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
            base_path = Path(base_dir).resolve() if base_dir else Path.cwd().resolve()
            return OpenApiSpec(raw_data=data, base_dir=base_path)
        except json.JSONDecodeError as exc:
            raise OpenApiSpecError(f"Malformed OpenAPI JSON string: {exc}")

    raise FileNotFoundError(f"OpenAPI specification file does not exist: {source}")
