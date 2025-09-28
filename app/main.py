"""FastAPI application exposing ggwave CLI helpers over HTTP."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Iterator

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GGWAVE_ENCODE_ENV = "GGWAVE_ENCODE"
GGWAVE_DECODE_ENV = "GGWAVE_DECODE"

DECODE_PATTERN = re.compile(r"\[\+] Decoded message with length \d+: '(.+?)'")


class EncodeRequest(BaseModel):
    """Payload describing the text that should be encoded into audio."""

    text: str = Field(..., description="Text that will be transformed into a WAV payload.")

    @property
    def stripped_text(self) -> str:
        """Return the message trimmed from surrounding whitespace."""

        return self.text.strip()


def _iter_default_cli_dirs() -> Iterator[Path]:
    """Yield directories that are likely to contain ggwave executables."""

    hints = [
        PROJECT_ROOT,
        PROJECT_ROOT / "external" / "ggwave",
        PROJECT_ROOT / "build",
        PROJECT_ROOT / "build" / "_deps" / "ggwave-build",
    ]
    subdirs = ["", "bin", "build", "build/bin", "build/examples", "examples"]

    seen: set[str] = set()
    for base in hints:
        for sub in subdirs:
            candidate = base if not sub else base / sub
            key = os.fspath(candidate)
            if key in seen:
                continue
            seen.add(key)
            yield candidate


def _possible_binary_names(name: str) -> list[str]:
    """Return executable names for the current platform."""

    variants = {name}
    if os.name == "nt" and not name.lower().endswith(".exe"):
        variants.add(f"{name}.exe")
    return sorted(variants)


def _ensure_cli_found(*, env_var: str, names: Iterable[str]) -> Path:
    """Locate a ggwave CLI executable.

    The lookup order honours the provided environment variable first, followed by a
    set of well-known build directories and finally the user's ``PATH``.
    """

    override = os.environ.get(env_var)
    if override:
        override_path = Path(override)
        if override_path.is_file():
            return override_path
        raise HTTPException(
            status_code=500,
            detail=(
                f"The environment variable {env_var} points to '{override}', but the"
                " executable could not be found."
            ),
        )

    candidate_names = [candidate for name in names for candidate in _possible_binary_names(name)]

    for directory in _iter_default_cli_dirs():
        for candidate in candidate_names:
            path_candidate = directory / candidate
            if path_candidate.is_file():
                return path_candidate

    for candidate in candidate_names:
        resolved = shutil.which(candidate)
        if resolved:
            return Path(resolved)

    names_str = ", ".join(candidate_names)
    raise HTTPException(
        status_code=500,
        detail=(
            f"Unable to locate a ggwave executable. Looked for: {names_str}. "
            f"Consider setting the {env_var} environment variable."
        ),
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


encoder_path = _ensure_cli_found(env_var=GGWAVE_ENCODE_ENV, names=["ggwave-to-file", "ggwave-cli"])
decoder_path = _ensure_cli_found(env_var=GGWAVE_DECODE_ENV, names=["ggwave-from-file"])

app = FastAPI(title="ALAI ggwave helpers")


def _build_encode_command(text: str, output_path: Path) -> tuple[list[str], bytes | None]:
    if not text:
        raise HTTPException(status_code=400, detail="Text to encode must not be empty.")

    executable = encoder_path.name.lower()
    if "ggwave-to-file" in executable:
        return [str(encoder_path), text, str(output_path)], None
    if "ggwave-cli" in executable:
        return [str(encoder_path), "--output", str(output_path)], text.encode("utf-8")

    raise HTTPException(
        status_code=500,
        detail=f"Unsupported encoder binary '{encoder_path}'.",
    )


@app.post(
    "/encode",
    response_class=StreamingResponse,
    summary="Encode text into an ultrasonic WAV payload",
)
async def encode(payload: EncodeRequest) -> StreamingResponse:
    text = payload.stripped_text
    if not text:
        raise HTTPException(status_code=400, detail="Text to encode must not be empty.")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
        command, input_data = _build_encode_command(text, tmp_path)
        _run_cli(command, input_data=input_data)

        audio_file = tmp_path.open("rb")
        try:
            response = StreamingResponse(audio_file, media_type="audio/wav")
            response.headers["Content-Disposition"] = 'attachment; filename="payload.wav"'
            return response
        except Exception:
            audio_file.close()
            raise
    finally:
        _remove_file(tmp_path)


@app.post(
    "/decode",
    response_class=PlainTextResponse,
    summary="Decode an ultrasonic WAV payload into text",
)
async def decode(file: UploadFile = File(..., description="WAV file generated by ggwave.")) -> PlainTextResponse:
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded WAV file was empty.")

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

