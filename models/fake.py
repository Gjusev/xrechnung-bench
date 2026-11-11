"""Offline FAKE adapter.

Returns canned JSON from fixtures/fake_model_output.json (a perfect extraction
of fixtures/invoices/invoice-001.xml). Used for end-to-end pipeline smoke
tests without GPU, PDF rendering or the KoSIT jar.
"""
from __future__ import annotations

import json

from .base import AdapterResult, BaseModelAdapter, FIXTURES


class FakeAdapter(BaseModelAdapter):
    model_id = "fake"

    def __init__(self, fixture_path: str | None = None):
        self.fixture_path = fixture_path or str(FIXTURES / "fake_model_output.json")
        with open(self.fixture_path, encoding="utf-8") as fh:
            payload = json.load(fh)
        if isinstance(payload, dict) and "predicted" in payload:
            payload = payload["predicted"]
        self._prediction = payload

    def run(self, document_path=None, doc_meta=None) -> dict:
        import copy

        out = AdapterResult(copy.deepcopy(self._prediction))
        out["_model_id"] = self.model_id
        out["_input"] = document_path
        return out
