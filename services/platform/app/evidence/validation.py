"""Does the file's content match what it claimed to be?

Slice 1 refused an unsupported *declared* media type before a byte was uploaded, and the
presigned policy binds that type into the signature so a client cannot upload under a
different label. Neither of those looks at the bytes. A client still controls what it
sends, so the file that arrives can be a `.exe` labelled `application/pdf`.

This is where that is caught, and it is deliberately in the worker rather than the API:
it needs the content, and reading document content in the request path is the thing M7
is arranged to avoid.

**Signatures, not a library.** The allowlist is four formats and their magic bytes are
stable to the point of being folklore. A dependency here would be a maintained detection
table in exchange for fifteen lines that will not change — and one more package parsing
attacker-controlled bytes.

What this does *not* do is decide whether a PDF is readable, has a text layer, or is
password-protected. Those need a parser, they belong with extraction, and they are
slice 3.
"""

from dataclasses import dataclass

#: Leading bytes that identify each supported format.
#:
#: HEIC has no signature at offset 0: it is an ISO base-media container whose `ftyp` box
#: sits at offset 4, so it is matched separately below rather than bent into this table.
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}

#: `ftyp` brands that mean HEIF/HEIC. Checked at offset 4, after the box length.
_HEIC_BRANDS = (b"heic", b"heix", b"hevc", b"heim", b"heis", b"hevm", b"mif1", b"msf1")

#: Enough for every signature above, and small enough to be a ranged read rather than a
#: download — the point is to reject a hostile file *before* anything parses it.
PREFIX_BYTES = 32


@dataclass(frozen=True)
class ContentCheck:
    matches: bool
    #: What the bytes look like, when that is knowable. Used for the log line and the
    #: user-facing summary; never the bytes themselves.
    detected: str | None


def _looks_like_heic(prefix: bytes) -> bool:
    return len(prefix) >= 12 and prefix[4:8] == b"ftyp" and prefix[8:12] in _HEIC_BRANDS


def detect(prefix: bytes) -> str | None:
    """The media type these leading bytes indicate, or None for unrecognised."""
    for media_type, signatures in _SIGNATURES.items():
        if any(prefix.startswith(signature) for signature in signatures):
            return media_type
    if _looks_like_heic(prefix):
        return "image/heic"
    return None


def check(prefix: bytes, *, declared: str) -> ContentCheck:
    """Whether the content agrees with the declared type.

    An empty file is not a document and cannot agree with anything, so it is reported as
    a mismatch with nothing detected rather than being quietly allowed through.
    """
    if not prefix:
        return ContentCheck(matches=False, detected=None)
    detected = detect(prefix)
    return ContentCheck(matches=detected == declared, detected=detected)
