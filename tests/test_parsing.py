# Copyright 2025 WhoMeta Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Parsing tests for UAP parsers.

Run with: pytest -q
"""
from unifiedagentprotocol.parser.openwebui import parse_openwebui
from unifiedagentprotocol.parser.openapi import parse_openapi
from unifiedagentprotocol.parser.langchain import parse_langchain


def test_parse_openwebui():
    data = {
        "name": "hello_world",
        "description": "Say hello",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Target name"}
            },
            "required": ["name"],
        },
    }
    tool = parse_openwebui(data)
    assert tool.name == "hello_world"
    assert tool.parameters[0].name == "name"


def test_parse_openapi():
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "Demo", "version": "1.0"},
        "paths": {
            "/greet": {
                "post": {
                    "summary": "Greet",
                    "operationId": "greet",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"name": {"type": "string"}},
                                    "required": ["name"],
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    tools = parse_openapi(spec)
    assert len(tools) == 1
    assert tools[0].name == "greet"


def test_parse_langchain():
    lc = {
        "name": "farewell",
        "description": "Say bye",
        "args_schema": {
            "name": {"type": "string", "description": "Name"}
        },
    }
    tool = parse_langchain(lc)
    assert tool.name == "farewell"
    assert any(p.name == "name" for p in tool.parameters)
