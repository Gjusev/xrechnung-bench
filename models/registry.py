"""Real model adapters — one per shortlisted model (see 4A research plan).

All of these require GPU inference stacks (vLLM, transformers, llama.cpp …)
that are deliberately NOT installed in the offline dev environment. Calling
run() raises NeedsGPUDeps with setup instructions pointing at docs/MAIN-PC.md.

Licenses verified on the HF model cards (2026-11-12, see README leaderboard):
PaddleOCR-VL-1.6 Apache-2.0, GLM-OCR MIT (layout pipeline Apache-2.0),
olmOCR-2-7B Apache-2.0, german-ocr-3 Apache-2.0, granite-docling-258M
Apache-2.0, Qwen3-VL-8B-Instruct Apache-2.0.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request
from pathlib import Path

from .base import AdapterResult, BaseModelAdapter, MissingCredentials, NeedsGPUDeps
from .fake import FakeAdapter

MAIN_PC = "docs/MAIN-PC.md"


def _require_module(name: str, install_hint: str, adapter: str) -> None:
    try:
        __import__(name)
    except ImportError as exc:
        raise NeedsGPUDeps(
            "%s requires the '%s' package (%s). Run this adapter on the GPU box — "
            "see %s. Missing: %s" % (adapter, name, install_hint, MAIN_PC, exc)
        ) from exc


class _LocalStubAdapter(BaseModelAdapter):
    """Base for local GPU adapters: vLLM server or transformers on the main PC."""

    model_id = "stub"
    hf_repo: str = ""
    license: str = ""
    deps: tuple = ()
    install_hint: str = ""

    def _check_deps(self) -> None:
        for mod in self.deps:
            _require_module(mod, self.install_hint, self.model_id)

    def run(self, document_path=None, doc_meta=None) -> dict:
        self._check_deps()
        raise NeedsGPUDeps(  # pragma: no cover - only reachable with deps installed
            "%s: inference path not wired in this checkout; run via the vLLM server "
            "recipe in %s" % (self.model_id, MAIN_PC)
        )


class PaddleOCRVLAdapter(_LocalStubAdapter):
    model_id = "paddleocr-vl-1.6"
    hf_repo = "PaddlePaddle/PaddleOCR-VL-1.6"
    license = "Apache-2.0"
    deps = ("paddleocr", "paddlepaddle")
    install_hint = "GPU vLLM server supported, ~4-6 GB VRAM"


class GLMOCRLocalAdapter(_LocalStubAdapter):
    model_id = "glm-ocr-local"
    hf_repo = "zai-org/GLM-OCR"
    license = "MIT (model; layout pipeline PP-DocLayoutV3 Apache-2.0)"
    deps = ("vllm",)
    install_hint = "vLLM/SGLang/Ollama, ~4-6 GB VRAM; use the strict-JSON info-extraction prompt"


class OLMOCRAdapter(_LocalStubAdapter):
    model_id = "olmocr-2-7b"
    hf_repo = "allenai/olmOCR-2-7B-1025"
    license = "Apache-2.0"
    deps = ("vllm", "torch")
    install_hint = "~16-20 GB BF16 / ~10 GB FP8"


class GermanOCRAdapter(_LocalStubAdapter):
    model_id = "german-ocr-3"
    hf_repo = "Keyven/german-ocr-3"
    license = "Apache-2.0"
    deps = ("llama_cpp",)
    install_hint = "GGUF ~2.7 GB, llama-cpp-python, ~4-6 GB VRAM"


class GraniteDoclingAdapter(_LocalStubAdapter):
    model_id = "granite-docling-258m"
    hf_repo = "ibm-granite/granite-docling-258M"
    license = "Apache-2.0"
    deps = ("transformers", "docling")
    install_hint = "~2-3 GB VRAM, DoclingDocuments JSON output"


class Qwen3VLAdapter(_LocalStubAdapter):
    model_id = "qwen3-vl-8b"
    hf_repo = "Qwen/Qwen3-VL-8B-Instruct"
    license = "Apache-2.0"
    deps = ("vllm", "torch")
    install_hint = "~18-22 GB BF16 / ~8-12 GB quantized; JSON-schema prompting"


class ApiZAIAdapter(BaseModelAdapter):
    """API reference model — runs via the Z.ai Coding Plan endpoint ONLY.

    OpenAI-compatible base URL: https://api.z.ai/api/coding/paas/v4
    Model pinned to glm-5.3-flash (owner decision; no other model id is offered).
    Key from env XBENCH_ZAI_KEY. On billing/endpoint errors this adapter raises:
    the pipeline STOPS and reports — it never falls back to pay-per-call
    providers or other endpoints.
    """

    model_id = "glm-5.3-flash-zai-api"
    base_url = "https://api.z.ai/api/coding/paas/v4"
    model_name = "glm-5.3-flash"

    def _api_key(self) -> str:
        key = os.environ.get("XBENCH_ZAI_KEY")
        if not key:
            raise MissingCredentials(
                "ApiZAIAdapter needs XBENCH_ZAI_KEY in the environment "
                "(Z.ai Coding Plan key). Offline tests stay key-free."
            )
        return key

    def _encode_image(self, document_path: str) -> str:
        p = Path(document_path)
        suffix = p.suffix.lower().lstrip(".") or "png"
        if suffix == "jpg":
            suffix = "jpeg"
        if suffix not in ("png", "jpeg", "webp", "pdf"):
            raise ValueError("unsupported document type for API reference: %s" % p.suffix)
        data = base64.b64encode(p.read_bytes()).decode("ascii")
        return "data:image/%s;base64,%s" % (suffix, data)

    def run(self, document_path=None, doc_meta=None) -> dict:
        self._api_key()  # credentials check before any request
        if not document_path:
            raise ValueError("ApiZAIAdapter requires a rendered document (image/PDF)")
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": self._encode_image(document_path)}},
                        {"type": "text", "text": self._prompt()},
                    ],
                }
            ],
            "temperature": 0,
        }
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self._api_key(),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Billing/quota/endpoint problems STOP the pipeline. No fallback.
            raise MissingCredentials(
                "Z.ai Coding Plan endpoint returned HTTP %s for %s — pipeline stopped, "
                "no pay-per-call fallback. Check plan quota/credentials: %s"
                % (exc.code, self.base_url, exc.read().decode("utf-8", "replace")[:500])
            ) from exc
        except urllib.error.URLError as exc:
            raise MissingCredentials(
                "Z.ai Coding Plan endpoint unreachable (%s): %s — pipeline stopped."
                % (self.base_url, exc.reason)
            ) from exc
        content = body["choices"][0]["message"]["content"]
        return AdapterResult(json.loads(_strip_code_fence(content)))

    @staticmethod
    def _prompt() -> str:
        return (
            "Extract the fields of this German invoice as strict JSON conforming to the "
            "xbench EN 16931 subset schema (BT-keyed keys: bt-1, bt-2, bt-3, bt-5, bt-9, "
            "bt-10, bt-27, bg-5, bt-31, bt-44, bg-8, bg-16, bg-25, bg-23, bg-22 as given in "
            "schema.json). Use null or \"not_found\" for fields you cannot read; never guess "
            "amounts or IBANs. Output JSON only."
        )


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


ADAPTER_REGISTRY: dict[str, type[BaseModelAdapter]] = {
    "fake": FakeAdapter,
    "paddleocr-vl-1.6": PaddleOCRVLAdapter,
    "glm-ocr-local": GLMOCRLocalAdapter,
    "olmocr-2-7b": OLMOCRAdapter,
    "german-ocr-3": GermanOCRAdapter,
    "granite-docling-258m": GraniteDoclingAdapter,
    "qwen3-vl-8b": Qwen3VLAdapter,
    "glm-5.3-flash-zai-api": ApiZAIAdapter,
}


def get_adapter(model_id: str) -> BaseModelAdapter:
    try:
        cls = ADAPTER_REGISTRY[model_id]
    except KeyError:
        raise KeyError("unknown model id %r — known: %s" % (model_id, ", ".join(ADAPTER_REGISTRY)))
    return cls()
