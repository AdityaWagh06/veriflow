"""
Unit tests for the OpenAPI Contract & Schema Validator (openapi_validator.py).
"""

from __future__ import annotations

import unittest

from skills.veriflow.scripts.openapi_loader import OpenApiOperation, load_openapi_spec
from skills.veriflow.scripts.openapi_validator import (
    SchemaValidationError,
    validate_api_response,
    validate_schema,
)


class TestOpenApiSchemaValidator(unittest.TestCase):
    """Test JSON schema validation and response contract checks."""

    def test_primitive_types_pass(self):
        self.assertEqual(validate_schema("hello", {"type": "string"}), [])
        self.assertEqual(validate_schema(42, {"type": "integer"}), [])
        self.assertEqual(validate_schema(3.14, {"type": "number"}), [])
        self.assertEqual(validate_schema(True, {"type": "boolean"}), [])
        self.assertEqual(validate_schema(None, {"type": "string", "nullable": True}), [])

    def test_primitive_type_mismatch(self):
        errs = validate_schema("not-a-number", {"type": "integer"})
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].error_type, "TYPE_MISMATCH")

        # Booleans should not be accepted as integers in Python
        errs_bool = validate_schema(True, {"type": "integer"})
        self.assertEqual(len(errs_bool), 1)
        self.assertEqual(errs_bool[0].error_type, "TYPE_MISMATCH")

    def test_enum_constraint(self):
        schema = {"type": "string", "enum": ["active", "inactive", "pending"]}
        self.assertEqual(validate_schema("active", schema), [])

        errs = validate_schema("deleted", schema)
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].error_type, "ENUM_VIOLATION")

    def test_numeric_boundaries(self):
        schema = {"type": "integer", "minimum": 10, "maximum": 100}
        self.assertEqual(validate_schema(10, schema), [])
        self.assertEqual(validate_schema(50, schema), [])
        self.assertEqual(validate_schema(100, schema), [])

        errs_under = validate_schema(9, schema)
        self.assertEqual(len(errs_under), 1)
        self.assertEqual(errs_under[0].error_type, "CONSTRAINT_VIOLATION")

        errs_over = validate_schema(101, schema)
        self.assertEqual(len(errs_over), 1)
        self.assertEqual(errs_over[0].error_type, "CONSTRAINT_VIOLATION")

    def test_string_length_and_pattern(self):
        schema = {"type": "string", "minLength": 3, "maxLength": 8, "pattern": r"^[A-Z]+$"}
        self.assertEqual(validate_schema("ABC", schema), [])
        self.assertEqual(validate_schema("ABCDEF", schema), [])

        self.assertTrue(any(e.error_type == "CONSTRAINT_VIOLATION" for e in validate_schema("AB", schema)))
        self.assertTrue(any(e.error_type == "CONSTRAINT_VIOLATION" for e in validate_schema("TOOLONGSTRING", schema)))
        self.assertTrue(any(e.error_type == "CONSTRAINT_VIOLATION" for e in validate_schema("abc", schema)))

    def test_object_required_properties(self):
        schema = {
            "type": "object",
            "required": ["id", "name", "price"],
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "price": {"type": "number"},
            },
        }

        valid_obj = {"id": 1, "name": "Widget", "price": 9.99}
        self.assertEqual(validate_schema(valid_obj, schema), [])

        missing_price = {"id": 1, "name": "Widget"}
        errs = validate_schema(missing_price, schema)
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].error_type, "MISSING_REQUIRED_FIELD")
        self.assertIn("price", errs[0].message)

    def test_additional_properties_forbidden(self):
        schema = {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "additionalProperties": False,
        }
        self.assertEqual(validate_schema({"id": 1}, schema), [])

        errs = validate_schema({"id": 1, "rogueField": "surprise"}, schema)
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].error_type, "ADDITIONAL_PROPERTY")

    def test_array_items_validation(self):
        schema = {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string"},
        }
        self.assertEqual(validate_schema(["a", "b"], schema), [])

        errs_empty = validate_schema([], schema)
        self.assertEqual(len(errs_empty), 1)
        self.assertEqual(errs_empty[0].error_type, "CONSTRAINT_VIOLATION")

        errs_item_type = validate_schema(["valid", 123], schema)
        self.assertEqual(len(errs_item_type), 1)
        self.assertEqual(errs_item_type[0].error_type, "TYPE_MISMATCH")
        self.assertEqual(errs_item_type[0].path, "$[1]")

    def test_validate_api_response_clean(self):
        operation = OpenApiOperation(
            path="/items",
            method="GET",
            responses={
                "200": {
                    "description": "List of items",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["id", "name"],
                                    "properties": {
                                        "id": {"type": "integer"},
                                        "name": {"type": "string"},
                                    },
                                },
                            }
                        }
                    },
                }
            },
        )

        headers = {"Content-Type": "application/json; charset=utf-8"}
        body = [{"id": 1, "name": "Item 1"}, {"id": 2, "name": "Item 2"}]

        errs = validate_api_response(operation, 200, headers, body)
        self.assertEqual(errs, [])

    def test_validate_api_response_unexpected_status(self):
        operation = OpenApiOperation(
            path="/items",
            method="GET",
            responses={"200": {"description": "OK"}},
        )
        errs = validate_api_response(operation, 500, {}, {})
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].error_type, "UNEXPECTED_STATUS_CODE")

    def test_validate_api_response_unexpected_content_type(self):
        operation = OpenApiOperation(
            path="/items",
            method="GET",
            responses={
                "200": {
                    "description": "OK",
                    "content": {"application/json": {"schema": {"type": "object"}}},
                }
            },
        )
        headers = {"Content-Type": "text/html"}
        errs = validate_api_response(operation, 200, headers, {})
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].error_type, "UNEXPECTED_CONTENT_TYPE")

    def test_validate_api_response_schema_violation(self):
        operation = OpenApiOperation(
            path="/items",
            method="GET",
            responses={
                "200": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["status", "count"],
                                "properties": {
                                    "status": {"type": "string"},
                                    "count": {"type": "integer"},
                                },
                            }
                        }
                    }
                }
            },
        )
        headers = {"Content-Type": "application/json"}
        # Missing count, status is int
        body = {"status": 123}
        errs = validate_api_response(operation, 200, headers, body)
        self.assertEqual(len(errs), 2)
        error_types = {e.error_type for e in errs}
        self.assertIn("MISSING_REQUIRED_FIELD", error_types)
        self.assertIn("TYPE_MISMATCH", error_types)


if __name__ == "__main__":
    unittest.main()
