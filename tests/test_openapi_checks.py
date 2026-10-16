"""
Unit tests for OpenAPI contract checks generator and execution dispatcher (openapi_checks.py).
"""

from __future__ import annotations

import unittest

from skills.veriflow.demo_app.server import DemoServer
from skills.veriflow.scripts.openapi_checks import (
    execute_contract_check,
    generate_contract_checks,
    run_openapi_contract_verification,
)
from skills.veriflow.scripts.openapi_loader import load_openapi_spec


class TestOpenApiChecks(unittest.TestCase):
    """Test check generation, preview mode, and execution dispatcher."""

    @classmethod
    def setUpClass(cls):
        cls.spec_doc = {
            "openapi": "3.0.3",
            "info": {"title": "Test Items API", "version": "1.0.0"},
            "paths": {
                "/api/health": {
                    "get": {
                        "operationId": "getHealth",
                        "summary": "Service health probe",
                        "responses": {
                            "200": {
                                "description": "Healthy",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["status"],
                                            "properties": {"status": {"type": "string"}},
                                        }
                                    }
                                },
                            }
                        },
                    }
                },
                "/api/items": {
                    "get": {
                        "operationId": "getItems",
                        "summary": "List items",
                        "responses": {
                            "200": {
                                "description": "Item list",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "required": ["id", "name", "price"],
                                                "properties": {
                                                    "id": {"type": "integer"},
                                                    "name": {"type": "string"},
                                                    "price": {"type": "number"},
                                                },
                                            },
                                        }
                                    }
                                },
                            }
                        },
                    },
                    "post": {
                        "operationId": "createItem",
                        "summary": "Create an item",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["name", "price"],
                                        "properties": {
                                            "name": {"type": "string"},
                                            "price": {"type": "number"},
                                        },
                                    }
                                }
                            },
                        },
                        "responses": {
                            "201": {
                                "description": "Created",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["id", "name", "price"],
                                            "properties": {
                                                "id": {"type": "integer"},
                                                "name": {"type": "string"},
                                                "price": {"type": "number"},
                                            },
                                        }
                                    }
                                },
                            }
                        },
                    },
                },
                "/api/profile": {
                    "get": {
                        "operationId": "getProfile",
                        "summary": "Protected user profile",
                        "security": [{"BearerAuth": []}],
                        "responses": {
                            "200": {
                                "description": "Profile",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["username"],
                                            "properties": {"username": {"type": "string"}},
                                        }
                                    }
                                },
                            },
                            "401": {"description": "Unauthorized"},
                        },
                    }
                },
            },
        }
        cls.spec = load_openapi_spec(cls.spec_doc)
        cls.server = DemoServer(port=0)
        cls.base_url = cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_generate_contract_checks(self):
        checks = generate_contract_checks(self.spec)
        check_ids = [c.check_id for c in checks]

        # Must include static spec validation
        self.assertIn("OA-SPEC-VALIDATION", check_ids)

        # Must include endpoints
        self.assertIn("OA-GET-/api/health", check_ids)
        self.assertIn("OA-GET-/api/items", check_ids)
        self.assertIn("OA-POST-/api/items", check_ids)

        # Must include auth enforcement on protected profile
        self.assertIn("OA-AUTH-GET-/api/profile", check_ids)

        # Must include input validation on POST /api/items (has required body)
        self.assertIn("OA-INPUT-POST-/api/items", check_ids)

    def test_preview_mode_makes_no_requests(self):
        report = run_openapi_contract_verification(
            self.spec,
            base_url=self.base_url,
            execute=False,
        )
        counts = report.summary_counts()
        self.assertEqual(counts["NOT_RUN"], len(report.results))
        self.assertEqual(counts["PASS"], 0)
        self.assertEqual(counts["FAIL"], 0)

    def test_static_spec_validation_passes(self):
        checks = generate_contract_checks(self.spec)
        spec_check = next(c for c in checks if c.check_id == "OA-SPEC-VALIDATION")
        result = execute_contract_check(spec_check, self.base_url, self.spec, execute=True)
        self.assertEqual(result.status, "PASS")
        self.assertIn("Valid OpenAPI", result.response_body_snippet or "")

    def test_external_target_blocked_by_default(self):
        checks = generate_contract_checks(self.spec)
        health_check = next(c for c in checks if c.check_id == "OA-GET-/api/health")
        result = execute_contract_check(
            health_check,
            base_url="https://api.external.com",
            spec=self.spec,
            allow_external=False,
            execute=True,
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("outside local loopback boundaries", result.error_message or "")

    def test_filter_checks(self):
        report = run_openapi_contract_verification(
            self.spec,
            base_url=self.base_url,
            execute=False,
            check_filter="health",
        )
        self.assertEqual(len(report.results), 1)
        self.assertEqual(report.results[0].test_id, "RESL-006")

    def test_live_execution_against_clean_demo_server(self):
        report = run_openapi_contract_verification(
            self.spec,
            base_url=self.base_url,
            execute=True,
        )
        counts = report.summary_counts()
        self.assertEqual(counts["FAIL"], 0)
        self.assertGreaterEqual(counts["PASS"], 4)


if __name__ == "__main__":
    unittest.main()
