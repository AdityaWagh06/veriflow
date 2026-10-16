"""
Unit tests for the OpenAPI Specification Loader and Safe Reference Resolver.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skills.veriflow.scripts.openapi_loader import (
    OpenApiBlockedError,
    OpenApiOperation,
    OpenApiSpec,
    OpenApiSpecError,
    load_openapi_spec,
)


class TestOpenApiLoader(unittest.TestCase):
    """Test specification loading, version checks, and reference resolution."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_valid_openapi_30_json(self):
        doc = {
            "openapi": "3.0.3",
            "info": {"title": "Sample API", "version": "1.0.0"},
            "paths": {
                "/items": {
                    "get": {
                        "operationId": "getItems",
                        "responses": {"200": {"description": "List items"}},
                    }
                }
            },
        }
        spec_path = self.base_path / "openapi.json"
        spec_path.write_text(json.dumps(doc), encoding="utf-8")

        spec = load_openapi_spec(spec_path)
        self.assertEqual(spec.version, "3.0.3")
        self.assertEqual(spec.title, "Sample API")
        self.assertEqual(spec.api_version, "1.0.0")

        ops = spec.get_operations()
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].path, "/items")
        self.assertEqual(ops[0].method, "GET")
        self.assertEqual(ops[0].operation_id, "getItems")

    def test_load_valid_openapi_31_dict(self):
        doc = {
            "openapi": "3.1.0",
            "info": {"title": "Next Gen API", "version": "2.0.0"},
            "paths": {},
        }
        spec = load_openapi_spec(doc)
        self.assertEqual(spec.version, "3.1.0")
        self.assertEqual(spec.title, "Next Gen API")

    def test_load_valid_openapi_yaml(self):
        yaml_content = """
openapi: 3.0.1
info:
  title: YAML Petstore
  version: 0.1.0
paths:
  /pets:
    post:
      summary: Create a pet
      responses:
        '201':
          description: Created
"""
        spec_path = self.base_path / "openapi.yaml"
        spec_path.write_text(yaml_content, encoding="utf-8")

        spec = load_openapi_spec(spec_path)
        self.assertEqual(spec.version, "3.0.1")
        self.assertEqual(spec.title, "YAML Petstore")
        ops = spec.get_operations()
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].method, "POST")

    def test_unsupported_swagger_20_rejected(self):
        doc = {
            "swagger": "2.0",
            "info": {"title": "Legacy API", "version": "1.0"},
            "paths": {},
        }
        with self.assertRaises(OpenApiSpecError) as ctx:
            load_openapi_spec(doc)
        self.assertIn("Unsupported legacy Swagger/OpenAPI version '2.0'", str(ctx.exception))

    def test_unsupported_openapi_version_rejected(self):
        doc = {
            "openapi": "4.0.0",
            "info": {"title": "Future API", "version": "1.0"},
            "paths": {},
        }
        with self.assertRaises(OpenApiSpecError) as ctx:
            load_openapi_spec(doc)
        self.assertIn("Unsupported OpenAPI version '4.0.0'", str(ctx.exception))

    def test_missing_required_fields(self):
        # Missing paths
        with self.assertRaises(OpenApiSpecError) as ctx:
            load_openapi_spec({"openapi": "3.0.0", "info": {"title": "T", "version": "1"}})
        self.assertIn("Missing required top-level object: 'paths'", str(ctx.exception))

        # Missing info.title
        with self.assertRaises(OpenApiSpecError) as ctx:
            load_openapi_spec({"openapi": "3.0.0", "info": {"version": "1"}, "paths": {}})
        self.assertIn("Missing required field in info object: 'title'", str(ctx.exception))

    def test_local_json_pointer_ref_resolution(self):
        doc = {
            "openapi": "3.0.0",
            "info": {"title": "Ref Test", "version": "1"},
            "paths": {
                "/item": {
                    "get": {
                        "responses": {
                            "200": {"$ref": "#/components/responses/ItemResponse"}
                        }
                    }
                }
            },
            "components": {
                "responses": {
                    "ItemResponse": {
                        "description": "Item description",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Item"}
                            }
                        },
                    }
                },
                "schemas": {
                    "Item": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "name": {"type": "string"},
                        },
                    }
                },
            },
        }
        spec = load_openapi_spec(doc)
        ops = spec.get_operations()
        self.assertEqual(len(ops), 1)
        resp_200 = ops[0].responses["200"]
        self.assertEqual(resp_200["description"], "Item description")

        # Resolve nested schema
        schema_ref = resp_200["content"]["application/json"]["schema"]
        resolved = spec.resolve_schema(schema_ref)
        self.assertEqual(resolved["type"], "object")
        self.assertIn("id", resolved["properties"])

    def test_circular_reference_handled_gracefully(self):
        doc = {
            "openapi": "3.0.0",
            "info": {"title": "Circular API", "version": "1"},
            "paths": {},
            "components": {
                "schemas": {
                    "Node": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "string"},
                            "next": {"$ref": "#/components/schemas/Node"},
                        },
                    }
                }
            },
        }
        spec = load_openapi_spec(doc)
        resolved = spec.resolve_schema({"$ref": "#/components/schemas/Node"})
        self.assertEqual(resolved["type"], "object")
        # Ensure it resolved first level and safely marked circular on recursion
        next_schema = resolved["properties"]["next"]
        self.assertTrue(next_schema.get("_circular") or "$ref" in next_schema)

    def test_remote_ref_blocked_by_safety(self):
        doc = {
            "openapi": "3.0.0",
            "info": {"title": "Remote Ref", "version": "1"},
            "paths": {},
            "components": {
                "schemas": {
                    "External": {"$ref": "https://example.com/schemas/remote.json"}
                }
            },
        }
        spec = load_openapi_spec(doc)
        with self.assertRaises(OpenApiSpecError) as ctx:
            spec.resolve_ref("https://example.com/schemas/remote.json")
        self.assertIn("Remote reference", str(ctx.exception))
        self.assertIn("blocked by Veriflow safety boundaries", str(ctx.exception))

    def test_path_traversal_ref_blocked(self):
        doc = {
            "openapi": "3.0.0",
            "info": {"title": "Traversal Test", "version": "1"},
            "paths": {},
        }
        spec_path = self.base_path / "spec.json"
        spec_path.write_text(json.dumps(doc), encoding="utf-8")
        spec = load_openapi_spec(spec_path)

        with self.assertRaises(OpenApiSpecError) as ctx:
            spec.resolve_ref("../../secret.json#/pwd")
        self.assertIn("Path traversal detected", str(ctx.exception))

    def test_parameter_merging_path_and_operation(self):
        doc = {
            "openapi": "3.0.0",
            "info": {"title": "Param API", "version": "1"},
            "paths": {
                "/users/{userId}": {
                    "parameters": [
                        {"name": "userId", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "X-Client", "in": "header", "required": False, "schema": {"type": "string"}},
                    ],
                    "get": {
                        "parameters": [
                            # Override X-Client with required=True
                            {"name": "X-Client", "in": "header", "required": True, "schema": {"type": "string"}},
                            {"name": "verbose", "in": "query", "schema": {"type": "boolean"}},
                        ],
                        "responses": {"200": {"description": "User"}},
                    },
                }
            },
        }
        spec = load_openapi_spec(doc)
        ops = spec.get_operations()
        params = ops[0].parameters
        self.assertEqual(len(params), 3)

        header_param = next(p for p in params if p["name"] == "X-Client")
        self.assertTrue(header_param["required"])

    def test_missing_pyyaml_raises_blocked_error(self):
        yaml_path = self.base_path / "spec.yaml"
        yaml_path.write_text("openapi: 3.0.0\ninfo:\n  title: T\n  version: 1\npaths: {}", encoding="utf-8")

        with patch.dict("sys.modules", {"yaml": None}):
            with self.assertRaises(OpenApiBlockedError) as ctx:
                load_openapi_spec(yaml_path)
            self.assertIn("PyYAML is not installed", str(ctx.exception))
            self.assertIn("Action: Install PyYAML", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
