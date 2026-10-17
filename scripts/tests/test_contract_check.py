import json

import pytest

from scripts.contract_check import compare_openapi, main


def old_schema():
    return {
        "openapi": "3.0.3",
        "paths": {
            "/api/v1/items/": {
                "get": {
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "requestBody": {"required": False},
                    "responses": {"201": {"description": "Created"}},
                },
            }
        },
    }


def test_backward_compatible_optional_additions():
    before = old_schema()
    after = old_schema()
    after["paths"]["/api/v1/new/"] = {"get": {"responses": {"200": {}}}}
    assert compare_openapi(before, after)["compatible"]


def test_removed_endpoint_and_new_required_field():
    before = old_schema()
    after = old_schema()
    after["paths"]["/api/v1/items/"]["get"]["parameters"][0]["required"] = True
    after["paths"]["/api/v1/items/"].pop("post")
    results = compare_openapi(before, after)
    assert results["compatible"] is False
    assert any("operation removed" in item for item in results["breaking"])
    assert any("new required query" in item for item in results["breaking"])


def test_detects_request_body_and_success_status_breaks():
    before = old_schema()
    after = old_schema()
    after["paths"]["/api/v1/items/"]["post"]["requestBody"]["required"] = True
    after["paths"]["/api/v1/items/"]["get"]["responses"] = {"204": {"description": "Empty"}}
    results = compare_openapi(before, after)
    assert any("request body became mandatory" in item for item in results["breaking"])
    assert any("successful response 200 removed" in item for item in results["breaking"])


def test_cli_exit_code_for_breaking_changes(tmp_path):
    previous = tmp_path / "before.json"
    current = tmp_path / "after.json"
    previous.write_text(json.dumps(old_schema()))
    broken = old_schema()
    broken["paths"] = {}
    current.write_text(json.dumps(broken))
    assert main([str(previous), str(current), "--fail-on-breaking", "--json"]) == 2
    with pytest.raises(ValueError):
        compare_openapi({}, {})


def test_path_level_required_parameter_added():
    before = old_schema()
    after = old_schema()
    after["paths"]["/api/v1/items/"]["parameters"] = [
        {"name": "tenant", "in": "header", "required": True}
    ]
    result = compare_openapi(before, after)
    assert any("required header parameter tenant" in item for item in result["breaking"])
