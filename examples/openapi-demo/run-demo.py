#!/usr/bin/env python3
"""
Veriflow OpenAPI Contract Verification Demo Runner.

Demonstrates contract-driven API verification against the deterministic local fixture:
1. Clean baseline: all mapped OpenAPI checks pass deterministically against openapi.json & openapi.yaml.
2. Fault injection mode: injects targeted defects into the demo server to prove that
   contract violations fail with clear, actionable diagnostics:
   - missing_field: response omits a required property
   - wrong_status: endpoint returns an undocumented status code
   - wrong_content_type: response content-type differs from documented schema
   - invalid_type: response property data type violates schema contract
   - request_validation: invalid request payload produces server crash instead of 400
3. Static validation mode (--validate-spec-only): validates specification syntax, schema rules,
   and reference integrity without starting the server or making any network requests.
4. Preview mode (--preview): displays planned contract verification checks without sending requests.

Usage:
    # 1. Preview planned contract checks
    python examples/openapi-demo/run-demo.py --preview

    # 2. Validate specification only
    python examples/openapi-demo/run-demo.py --validate-spec-only

    # 3. Run clean demo suite against JSON spec
    python examples/openapi-demo/run-demo.py

    # 4. Run clean demo suite against YAML spec
    python examples/openapi-demo/run-demo.py --yaml

    # 5. Fault injection: missing required field
    python examples/openapi-demo/run-demo.py --fault missing_field

    # 6. Fault injection: wrong status code
    python examples/openapi-demo/run-demo.py --fault wrong_status

    # 7. Fault injection: unexpected content type
    python examples/openapi-demo/run-demo.py --fault wrong_content_type

    # 8. Fault injection: invalid data type
    python examples/openapi-demo/run-demo.py --fault invalid_type

    # 9. Test deliberately broken specification
    python examples/openapi-demo/run-demo.py --spec examples/openapi-demo/specs/missing_fields.json --validate-spec-only
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys

# Ensure repository root is on sys.path
DEMO_DIR = Path(__file__).resolve().parent
REPO_ROOT = DEMO_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load run_openapi_cli from run-openapi-tests.py
CLI_SCRIPT = REPO_ROOT / "skills" / "veriflow" / "scripts" / "run-openapi-tests.py"
spec = importlib.util.spec_from_file_location("run_openapi_tests_module", CLI_SCRIPT)
run_openapi_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_openapi_module)
run_openapi_cli = run_openapi_module.run_openapi_cli

try:
    from server import OpenApiDemoServer
except ImportError:
    server_script = DEMO_DIR / "server.py"
    spec_server = importlib.util.spec_from_file_location("openapi_demo_server_module", server_script)
    mod_server = importlib.util.module_from_spec(spec_server)
    spec_server.loader.exec_module(mod_server)
    OpenApiDemoServer = mod_server.OpenApiDemoServer


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Veriflow OpenAPI Contract Verification Demo Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--spec",
        default=str(DEMO_DIR / "openapi.json"),
        help="Path to OpenAPI specification (defaults to examples/openapi-demo/openapi.json)",
    )
    parser.add_argument(
        "--yaml",
        action="store_true",
        help="Shortcut to use examples/openapi-demo/openapi.yaml",
    )
    parser.add_argument(
        "--fault",
        choices=["missing_field", "wrong_status", "wrong_content_type", "invalid_type", "request_validation"],
        help="Inject a targeted contract fault into the demo server",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview generated contract checks without sending any network requests",
    )
    parser.add_argument(
        "--validate-spec-only",
        action="store_true",
        help="Validate OpenAPI specification syntax and reference integrity only (zero network requests)",
    )
    parser.add_argument(
        "--check",
        dest="check_filter",
        help="Filter checks by operationId or check name",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--base-url",
        help="Optional external target URL override (defaults to local OpenApiDemoServer)",
    )

    args = parser.parse_args()

    spec_file = DEMO_DIR / "openapi.yaml" if args.yaml else Path(args.spec)
    as_json = args.format == "json"

    # Static validation or Preview mode (no server needed)
    if args.preview or args.validate_spec_only:
        return run_openapi_cli(
            spec_path=str(spec_file),
            target_url=args.base_url or "http://127.0.0.1:8080",
            execute=False,
            validate_spec_only=args.validate_spec_only,
            check_filter=args.check_filter,
            as_json=as_json,
        )

    # Live execution: start local fixture if base_url is not explicitly provided
    server = None
    target_url = args.base_url
    if not target_url:
        server = OpenApiDemoServer(host="127.0.0.1", port=0, fault=args.fault or "")
        target_url = server.start()
        if not as_json:
            print(f"[Demo] Started local OpenAPI test fixture at {target_url} (fault: {args.fault or 'none'})")

    try:
        return run_openapi_cli(
            spec_path=str(spec_file),
            target_url=target_url,
            execute=True,
            validate_spec_only=False,
            check_filter=args.check_filter,
            as_json=as_json,
        )
    finally:
        if server:
            server.stop()
            if not as_json:
                print("[Demo] Stopped local OpenAPI test fixture.")


if __name__ == "__main__":
    sys.exit(main())
