"""FastAPI application exposing ggwave CLI helpers over HTTP."""

from __future__ import annotations

import io
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Sequence, Tuple

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GGWAVE_BINARY_DIRS: Sequence[Path] = (
    PROJECT_ROOT / "build" / "_deps" / "ggwave-build" / "bin",
    PROJECT_ROOT / "external" / "ggwave" / "build" / "bin",
)
DECODE_PATTERN = re.compile(r"Decoded message with length \d+: '([^']*)'")

app = FastAPI(
    title="AudioLink BE",
    description="HTTP wrapper around ggwave CLI utilities for ultrasonic data transfer.",
    version="0.1.0",
)

_default_origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]
if not _default_origins:
    _default_origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/__routes")
def _list_routes() -> dict[str, list[str | None]]:
    return {"routes": [getattr(r, "path", None) for r in app.routes]}


@app.on_event("startup")
async def _log_routes() -> None:
    print("ROUTES:", [r.path for r in app.routes])


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


def _resolve_cli_path(
    value: str | None,
    *,
    binary_names: Sequence[str],
) -> Tuple[Path, str, bool]:
    """Resolve CLI paths, allowing relative values via environment variables."""

    search_paths: list[tuple[Path, str]] = []

    if value:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        search_paths.append((candidate, "environment"))

    for name in binary_names:
        for directory in GGWAVE_BINARY_DIRS:
            search_paths.append((directory / name, "default"))

    if not search_paths:
        raise HTTPException(status_code=500, detail="No CLI search paths configured.")

    for path, origin in search_paths:
        if path.exists() and path.is_file():
            return path, origin, True

    return search_paths[0][0], search_paths[0][1], False


def _resolve_decoder_path() -> Tuple[Path, str, bool]:
    return _resolve_cli_path(
        os.environ.get("GGWAVE_DECODE"),
        binary_names=("ggwave-from-file", "ggwave-from-file.exe"),
    )


def _resolve_encoder_path() -> Tuple[Path, str, bool]:
    return _resolve_cli_path(
        os.environ.get("GGWAVE_ENCODE"),
        binary_names=("ggwave-to-file", "ggwave-to-file.exe"),
    )


def _run_cli(command: Iterable[str], *, input_data: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            list(command),
            input=input_data,
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover - file missing is handled as runtime error
        raise HTTPException(status_code=500, detail=f"Executable not found: {command!r}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode("utf-8", errors="ignore").strip()
        detail = stderr or f"Command '{' '.join(map(str, command))}' failed with exit code {exc.returncode}"
        raise HTTPException(status_code=500, detail=detail) from exc


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


class EncodeRequest(BaseModel):
    """Request payload for the encode endpoint."""

    text: str


def _ensure_cli_found(path: Path, origin: str, message: str) -> None:
    if path.exists() and path.is_file():
        return

    if origin == "environment":
        hint = (
            f"{message} not found at {path}. Verify the environment variable or rebuild the binaries "
            "with 'make build-ggwave'."
        )
    else:
        hint = (
            f"{message} not found. Run 'make build-ggwave' so the binary is available at {path}."
        )
    raise HTTPException(status_code=500, detail=hint)


@app.post(
    "/encode",
    response_class=StreamingResponse,
    summary="Encode text into an ultrasonic WAV payload",
)
def encode(payload: EncodeRequest) -> StreamingResponse:
    """Invoke the ggwave encoder CLI and stream the resulting WAV file."""

    if payload.text.strip() == "":
        raise HTTPException(status_code=400, detail="Field 'text' must not be empty.")

    encoder_path, origin, found = _resolve_encoder_path()
    if not found:
        _ensure_cli_found(encoder_path, origin, "Encoder CLI")

    result = _run_cli([str(encoder_path)], input_data=(payload.text + "\n").encode("utf-8"))
    wav_bytes = result.stdout

    if not wav_bytes:
        raise HTTPException(status_code=500, detail="Encoder CLI produced no audio output.")

    buffer = io.BytesIO(wav_bytes)
    buffer.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="link.wav"'}
    return StreamingResponse(buffer, media_type="audio/wav", headers=headers)


@app.post(
    "/decode",
    response_class=PlainTextResponse,
    summary="Decode an ultrasonic WAV payload into text",
)
async def decode(file: UploadFile = File(..., description="WAV file generated by ggwave.")) -> PlainTextResponse:
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded WAV file was empty.")

    decoder_path, origin, found = _resolve_decoder_path()
    if not found:
        _ensure_cli_found(decoder_path, origin, "Decoder CLI")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
        tmp_file.write(contents)
        tmp_path = Path(tmp_file.name)

    try:
        result = _run_cli([str(decoder_path), str(tmp_path)])
    finally:
        _remove_file(tmp_path)

    decoded_output = result.stdout.decode("utf-8", errors="ignore")
    match = DECODE_PATTERN.search(decoded_output)
    if not match:
        raise HTTPException(
            status_code=400,
            detail="Could not decode a message from the provided audio.",
        )

    message = match.group(1)
    return PlainTextResponse(content=message)
