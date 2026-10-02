import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)(?:\.\s+|\s+)(.+)$")
_PAGE_FOOTER_RE = re.compile(r"^Página\s+\d+\s*$")
_VERSION_RE = re.compile(r"Versão\s+(\d+\.\d+)")

_NOISE_LINES = {
    "Empório da Música Manual de Políticas e Procedimentos",
    "Empório da Música — Sua música começa aqui.",
}

# Characters that appear as stray markers in the source PDF.
_STRIP_CHARS = "\u200b\u200c\u00a0\u202f"


@dataclass(frozen=True)
class PolicyChunk:
    section: str
    title: str
    text: str


def extract_pdf_text(path: Path) -> str:
    doc = pymupdf.open(str(path))
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def detect_source_version(text: str) -> str:
    match = _VERSION_RE.search(text)
    return match.group(1) if match else "unknown"


def _clean_line(line: str) -> str:
    line = line.strip().strip(_STRIP_CHARS).strip()
    if line == "•":
        return ""
    return line


def _is_noise(line: str) -> bool:
    if line in _NOISE_LINES:
        return True
    if _PAGE_FOOTER_RE.match(line):
        return True
    if line.startswith("Última atualização:"):
        return True
    return False


def chunk_policy(text: str) -> list[PolicyChunk]:
    chunks: list[PolicyChunk] = []
    current: tuple[str, str, list[str]] | None = None
    current_top = 0

    def flush() -> None:
        nonlocal current
        if current is not None:
            section, title, lines = current
            body = "\n".join(lines).strip()
            if body:
                chunks.append(PolicyChunk(section=section, title=title, text=body))

    for raw_line in text.splitlines():
        line = _clean_line(raw_line)
        if not line or _is_noise(line):
            continue

        match = _HEADING_RE.match(line)
        if match:
            number = match.group(1)
            title = match.group(2).strip()
            if "." in number or int(number) > current_top:
                flush()
                if "." not in number:
                    current_top = int(number)
                current = (number, title, [])
                continue

        if current is not None:
            current[2].append(line)

    flush()
    return chunks
