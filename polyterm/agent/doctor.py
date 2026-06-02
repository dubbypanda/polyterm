"""Agent installation and tool-surface diagnostics."""

import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..api.clob import CLOBClient
from ..api.data_api import DataAPIClient
from ..db.database import Database
from .registry import get_manifest, get_tools


class AgentDoctor:
    """Run bounded diagnostics for PolyTerm agent integrations."""

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        data_api_factory: Callable[[], DataAPIClient] = DataAPIClient,
        clob_factory: Callable[[], CLOBClient] = CLOBClient,
        database_factory: Callable[[], Database] = Database,
    ):
        self.repo_root = repo_root or Path(__file__).resolve().parents[2]
        self.data_api_factory = data_api_factory
        self.clob_factory = clob_factory
        self.database_factory = database_factory

    def run(self, skip_network: bool = False, check_mcp: bool = True) -> Dict[str, Any]:
        checks = [
            self._schema_files(),
            self._manifest_sync(),
            self._sqlite_archive(),
            self._hermes_config(),
        ]
        if check_mcp:
            checks.append(self._mcp_server_boot())
        if skip_network:
            checks.extend([
                _check("data_api_connectivity", "skipped", "Skipped by request."),
                _check("clob_api_connectivity", "skipped", "Skipped by request."),
            ])
        else:
            checks.extend([self._data_api_connectivity(), self._clob_api_connectivity()])

        return {
            "summary": self._summary(checks),
            "checks": checks,
            "hermes_config": {
                "mcp_servers": {
                    "polyterm": {
                        "command": "polyterm",
                        "args": ["agent", "mcp-server"],
                        "timeout": 120,
                        "connect_timeout": 60,
                    }
                }
            },
            "quality_flags": ["agent_doctor", "no_custody", "bounded_diagnostics"],
        }

    def _schema_files(self) -> Dict[str, Any]:
        missing = []
        invalid = []
        for tool in get_tools():
            path = self.repo_root / tool.schema
            if not path.exists():
                missing.append(tool.schema)
                continue
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                invalid.append({"path": tool.schema, "error": str(exc)})

        if missing or invalid:
            return _check(
                "schema_files",
                "error",
                "One or more documented schemas are missing or invalid.",
                {"missing": missing, "invalid": invalid},
            )
        return _check("schema_files", "ok", "All registry schema files exist and parse as JSON.")

    def _manifest_sync(self) -> Dict[str, Any]:
        static_path = self.repo_root / "docs/tool-manifest.json"
        runtime_tools = {tool["name"]: tool for tool in get_manifest()["tools"]}
        if not static_path.exists():
            return _check("manifest_sync", "error", "docs/tool-manifest.json is missing.")

        static = json.loads(static_path.read_text(encoding="utf-8"))
        static_tools = {tool["name"]: tool for tool in static.get("tools", [])}
        missing_static = sorted(set(runtime_tools) - set(static_tools))
        extra_static = sorted(set(static_tools) - set(runtime_tools))
        schema_mismatches = sorted(
            name
            for name in set(runtime_tools) & set(static_tools)
            if runtime_tools[name].get("schema") != static_tools[name].get("schema")
        )

        if missing_static or extra_static or schema_mismatches:
            return _check(
                "manifest_sync",
                "error",
                "Runtime registry and docs/tool-manifest.json differ.",
                {
                    "missing_static": missing_static,
                    "extra_static": extra_static,
                    "schema_mismatches": schema_mismatches,
                },
            )
        return _check("manifest_sync", "ok", "Runtime registry and static tool manifest are in sync.")

    def _mcp_server_boot(self) -> Dict[str, Any]:
        try:
            from .mcp.fastmcp_server import create_server

            server = create_server()
            names = _list_mcp_tool_names(server)
            details: Dict[str, Any] = {"server": "polyterm"}
            if names is not None:
                runtime_names = {tool.name for tool in get_tools()}
                mcp_names = set(names)
                details.update(
                    {
                        "tool_count": len(names),
                        "missing_mcp_tools": sorted(runtime_names - mcp_names),
                    }
                )
                if details["missing_mcp_tools"]:
                    return _check("mcp_server_boot", "error", "FastMCP server is missing registry tools.", details)
            return _check("mcp_server_boot", "ok", "FastMCP server can be constructed.", details)
        except Exception as exc:
            return _check("mcp_server_boot", "error", "FastMCP server could not be constructed.", {"error": str(exc)})

    def _data_api_connectivity(self) -> Dict[str, Any]:
        client = self.data_api_factory()
        try:
            rows = client.get_recent_trades(limit=1)
            return _check(
                "data_api_connectivity",
                "ok",
                "Polymarket Data API trade tape responded.",
                {"rows": len(rows) if isinstance(rows, list) else None},
            )
        except Exception as exc:
            return _check("data_api_connectivity", "warn", "Polymarket Data API check failed.", {"error": str(exc)})
        finally:
            if hasattr(client, "close"):
                client.close()

    def _clob_api_connectivity(self) -> Dict[str, Any]:
        client = self.clob_factory()
        try:
            markets = client.get_current_markets(limit=1)
            return _check(
                "clob_api_connectivity",
                "ok",
                "CLOB sampling markets endpoint responded.",
                {"rows": len(markets) if isinstance(markets, list) else None},
            )
        except Exception as exc:
            return _check("clob_api_connectivity", "warn", "CLOB API check failed.", {"error": str(exc)})
        finally:
            if hasattr(client, "close"):
                client.close()

    def _sqlite_archive(self) -> Dict[str, Any]:
        try:
            db = self.database_factory()
            stats = db.get_database_stats()
            return _check("sqlite_archive", "ok", "Local SQLite archive is readable.", {"tables": stats})
        except Exception as exc:
            return _check("sqlite_archive", "error", "Local SQLite archive check failed.", {"error": str(exc)})

    def _hermes_config(self) -> Dict[str, Any]:
        return _check("hermes_config", "ok", "Hermes MCP config snippet is available in doctor output.")

    def _summary(self, checks: List[Dict[str, Any]]) -> Dict[str, Any]:
        counts = {"ok": 0, "warn": 0, "error": 0, "skipped": 0}
        for check in checks:
            counts[check["status"]] = counts.get(check["status"], 0) + 1
        return {
            "status": "error" if counts["error"] else "warn" if counts["warn"] else "ok",
            "ok": counts["ok"],
            "warn": counts["warn"],
            "error": counts["error"],
            "skipped": counts["skipped"],
        }


def _list_mcp_tool_names(server: Any) -> Optional[List[str]]:
    try:
        tools = asyncio.run(server.list_tools())
    except RuntimeError:
        return None
    return [tool.name for tool in tools]


def _check(name: str, status: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "message": message,
        "details": details or {},
    }
