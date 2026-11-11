"""Adapter contract.

Every model in the benchmark implements this interface. Adapters take a
document (page image or PDF path) and return structured JSON conforming to
schema.json (EN 16931 subset). Models NEVER return or write XML — the
deterministic builder in models/xml_builder.py owns that step.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "fixtures"


class NeedsGPUDeps(Exception):
    """Raised by real adapters when the heavy inference dependency stack is absent.

    The message must name the missing deps and point at docs/MAIN-PC.md.
    """


class MissingCredentials(Exception):
    """Raised when an adapter needs an API key that is not configured."""


class AdapterResult(dict):
    """dict with metadata about how the prediction was produced."""


def load_schema() -> dict:
    with open(REPO_ROOT / "schema.json", encoding="utf-8") as fh:
        return json.load(fh)


def resolve_field(value: Any) -> tuple[Any, bool]:
    """Resolve a schema.json field value to (concrete_value_or_None, uncertain).

    Handles the abstention conventions from schema.json:
      * absent key            -> (None, False)
      * None                  -> (None, False)
      * "not_found"           -> (None, False)
      * {"value": x, "uncertain": true} -> (x, True)
      * anything else         -> (value, False)
    """
    if value is None or value == "" or value == "not_found":
        return None, False
    if isinstance(value, dict) and "value" in value:
        inner = value["value"]
        if inner in (None, "", "not_found"):
            return None, bool(value.get("uncertain"))
        return inner, bool(value.get("uncertain"))
    return value, False


class BaseModelAdapter:
    """Interface every adapter implements."""

    model_id: str = "abstract"

    def run(self, document_path: str | None, doc_meta: dict | None = None) -> dict:
        """Return predicted instance (schema.json shape) for one document.

        document_path: rendered page image / PDF of the invoice (may be None for
        adapters that don't need it, e.g. the offline fake). doc_meta: corpus
        manifest entry (layout, tier, seeds) — never the ground-truth values.
        """
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - resource hook
        pass
