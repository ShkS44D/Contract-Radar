"""Static OpenAPI contract; no external UI assets are needed."""

SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Solidity Sentinel API",
        "version": "2.0.0",
        "description": "Asynchronous static analysis. Only completed scans have scores.",
    },
    "paths": {
        "/api/v1/scan": {
            "post": {
                "summary": "Upload a Solidity source or ZIP project",
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "required": ["contract"],
                                "properties": {"contract": {"type": "string", "format": "binary"}},
                            }
                        }
                    },
                },
                "responses": {
                    "202": {
                        "description": "Queued; Location is the polling URL",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ScanResult"}
                            }
                        },
                    },
                    **{
                        str(code): {"description": message}
                        for code, message in [
                            (400, "Invalid upload"),
                            (413, "Too large"),
                            (429, "Rate limited"),
                            (503, "Queue full"),
                        ]
                    },
                },
            }
        },
        "/api/v1/scan/{scan_id}": {
            "get": {
                "summary": "Read state and report",
                "parameters": [
                    {
                        "in": "path",
                        "name": "scan_id",
                        "required": True,
                        "schema": {"type": "string", "format": "uuid"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Current state",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ScanResult"}
                            }
                        },
                    },
                    "404": {"description": "Not found or expired"},
                },
            }
        },
    },
    "components": {
        "schemas": {
            "Finding": {
                "type": "object",
                "required": [
                    "id",
                    "rule_id",
                    "severity",
                    "confidence",
                    "file",
                    "line_start",
                    "line_end",
                    "description",
                    "remediation",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "rule_id": {"type": "string"},
                    "title": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low", "info", "gas"],
                    },
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "file": {"type": "string"},
                    "line_start": {"type": "integer", "minimum": 1},
                    "line_end": {"type": "integer", "minimum": 1},
                    "snippet": {"type": "string"},
                    "description": {"type": "string"},
                    "remediation": {"type": "string"},
                    "swc": {"type": "string", "nullable": True},
                    "cwe": {"type": "string", "nullable": True},
                },
            },
            "ScanResult": {
                "type": "object",
                "required": ["scan_id", "state", "filename", "findings", "metadata", "score"],
                "properties": {
                    "scan_id": {"type": "string", "format": "uuid"},
                    "state": {
                        "type": "string",
                        "enum": [
                            "queued",
                            "running",
                            "completed",
                            "compile_error",
                            "timeout",
                            "engine_error",
                        ],
                    },
                    "filename": {"type": "string"},
                    "findings": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/Finding"},
                    },
                    "metadata": {"type": "object"},
                    "diagnostics": {"type": "string"},
                    "score": {"type": "integer", "minimum": 0, "maximum": 100, "nullable": True},
                    "grade": {"type": "string", "nullable": True},
                    "risk": {"type": "string", "nullable": True},
                    "breakdown": {"type": "array", "items": {"type": "object"}},
                },
            },
        }
    },
}
