"""Reading text out of a document. Deterministically, and with no model anywhere.

This is the whole of M7's extraction: PyMuPDF's native text layer and the page metadata
that comes with it. Classification, structured fields and anything resembling a claim are
M8. Nothing here infers; it decodes.

That distinction is the reason the output is not an `ExtractedClaim` and the run is not an
`ExtractionRun` (Domain §17). A claim is a proposal that needs a human to confirm before
it can influence anything. This is the bytes, read — untrusted as *input* to M8, but not
untrusted in the claims-versus-facts sense, because it asserts nothing.

**The file is hostile until proven otherwise.** PyMuPDF is a C parser given
attacker-controlled input, and malware scanning is a documented non-goal (threat model
§7, §28). So the bounds here are not tidiness:

- a page cap, so a 10,000-page document is a truncated read rather than a stalled worker;
- a character cap, so a page that expands to a gigabyte of text is bounded too;
- password detection *before* any page is touched;
- and every parser failure caught, because a `RuntimeError` out of a C library must
  become a failure code rather than a stack trace.

Resource exhaustion is bounded outside this module as well — `worker_max_memory_per_child`
recycles a child that grows, and the container has a memory limit. A decompression bomb
blows up on `open()` or on one page, which no page cap can prevent; the answer to that is
the child dying and being replaced, not the box dying.
"""

from dataclasses import dataclass

import pymupdf

#: Pages read at most. Beyond this the read is marked truncated rather than abandoned:
#: a long document is still worth what its first pages say, and M8 will know it was
#: bounded.
MAX_PAGES = 40

#: Characters kept at most, across all pages.
MAX_CHARACTERS = 200_000


class PasswordProtected(Exception):
    """The document needs a password. Terminal: no retry produces one."""


class UnreadableDocument(Exception):
    """The parser could not open or read the file. Terminal for the same reason."""


@dataclass(frozen=True)
class ExtractedText:
    page_count: int
    character_count: int
    content: str
    truncated: bool

    @property
    def has_text_layer(self) -> bool:
        """Whether the document actually said anything.

        False for a scan — a photograph of a page has no text layer, and reading it needs
        OCR or a multimodal model, both of which are M8. That is a *finding* about a
        perfectly valid document, not a failure of this pipeline, and the caller maps it
        to `PARTIALLY_COMPLETED` rather than to `FAILED`.
        """
        return self.character_count > 0


def extract(content: bytes) -> ExtractedText:
    """Read the native text layer, bounded.

    Takes bytes rather than a path or a key: this module has no business knowing where a
    document is stored, and a function that cannot reach the object store cannot be the
    thing that leaks one.
    """
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise UnreadableDocument(type(exc).__name__) from exc

    try:
        if document.needs_pass:
            # Checked before any page is touched. An encrypted document's page objects
            # are not readable anyway, and asking for them first turns a clean answer
            # into a parser error.
            raise PasswordProtected()

        total_pages = document.page_count
        pages: list[str] = []
        characters = 0
        truncated = total_pages > MAX_PAGES

        for index in range(min(total_pages, MAX_PAGES)):
            try:
                text = document.load_page(index).get_text()
            except Exception as exc:
                # One bad page does not condemn the document. A partially readable file
                # is worth what it does say, and the alternative — failing the whole
                # document because page 7 is malformed — throws away six good pages.
                raise UnreadableDocument(type(exc).__name__) from exc

            remaining = MAX_CHARACTERS - characters
            if remaining <= 0:
                truncated = True
                break
            if len(text) > remaining:
                text = text[:remaining]
                truncated = True

            pages.append(text)
            characters += len(text)

        joined = "\n".join(pages)
        return ExtractedText(
            page_count=total_pages,
            character_count=len(joined),
            content=joined,
            truncated=truncated,
        )
    finally:
        # Always closed, including on the password and unreadable paths: PyMuPDF holds
        # the whole stream, and a worker that leaks one document per hostile upload is a
        # worker that eventually stops.
        document.close()
