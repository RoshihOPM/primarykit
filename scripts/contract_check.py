#!/usr/bin/env python3
"""Offline JSON OpenAPI checks for backward-compatibility review."""

import argparse
import json
from pathlib import Path

_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})


def _required_parameters(operation: dict) -> set[tuple[str, str]]:
    return {
        (item["in"], item["name"])
        for item in operation.get("parameters", [])
        if isinstance(item, dict)
        and item.get("required", False)
        and "name" in item
        and "in" in item
    }


def compare_openapi(before: dict, after: dict) -> dict:
    """Detect a conservative subset of breaking changes. Never silently rewrite APIs."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError("OpenAPI inputs must be objects")
    old_paths = before.get("paths")
    new_paths = after.get("paths")
    if not isinstance(old_paths, dict) or not isinstance(new_paths, dict):
        raise ValueError("OpenAPI documents must contain path mappings")
    breaking = []
    warnings = []
    for path, route in old_paths.items():
        if not isinstance(route, dict):
            raise ValueError("Invalid old path item")
        current = new_paths.get(path)
        for method, old_op in route.items():
            if method not in _METHODS:
                continue
            label = f"{method.upper()} {path}"
            if not isinstance(current, dict) or method not in current:
                breaking.append(f"{label}: operation removed")
                continue
            new_op = current[method]
            if not isinstance(old_op, dict) or not isinstance(new_op, dict):
                raise ValueError("OpenAPI operation must be an object")
            old_required = _required_parameters(route) | _required_parameters(old_op)
            new_required = _required_parameters(current) | _required_parameters(new_op)
            for location, name in sorted(new_required - old_required):
                breaking.append(f"{label}: new required {location} parameter {name}")
            if not old_op.get("requestBody", {}).get("required", False) and new_op.get(
                "requestBody", {}
            ).get("required", False):
                breaking.append(f"{label}: request body became mandatory")
            old_success = {key for key in old_op.get("responses", {}) if str(key).startswith("2")}
            new_success = {key for key in new_op.get("responses", {}) if str(key).startswith("2")}
            for code in sorted(old_success - new_success):
                breaking.append(f"{label}: successful response {code} removed")
            if old_op.get("responses") != new_op.get("responses"):
                warnings.append(f"{label}: response schemas require manual review")
            if old_op.get("security") != new_op.get("security"):
                warnings.append(f"{label}: authorization requirements may have changed")
            for op in (old_op, new_op):
                if any(
                    isinstance(item, dict) and "$ref" in item for item in op.get("parameters", [])
                ):
                    warnings.append(f"{label}: referenced parameters need manual review")
    return {
        "breaking": sorted(set(breaking)),
        "warnings": sorted(set(warnings)),
        "compatible": not breaking,
        "note": "Does not prove schema, tenant permission, or behavioral compatibility.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two OpenAPI 3.x JSON documents")
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-breaking", action="store_true")
    args = parser.parse_args(argv)
    result = compare_openapi(
        json.loads(args.before.read_text(encoding="utf-8")),
        json.loads(args.after.read_text(encoding="utf-8")),
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        for item in result["breaking"]:
            print(f"BREAKING: {item}")
        for item in result["warnings"]:
            print(f"REVIEW: {item}")
        print(
            "No detected breaking changes."
            if result["compatible"]
            else "Breaking changes detected."
        )
    return 2 if args.fail_on_breaking and result["breaking"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
