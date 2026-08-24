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
§7, §28). The bounds here are not tidiness, and they come in two kinds, because the first
kind is not enough:

- **Output bounds** — a page cap and a character cap. These stop a 10,000-page document
  and a page that decodes to a gigabyte of text.
- **A work bound** — a wall-clock deadline. This is the one that matters, and it was
  missing. A page cap bounds *how much comes out*, not *how much it costs to get*: a
  single-page PDF whose content stream nests Form XObjects, each invoking the next twice,
  costs exponential time inside one `get_text()` call and produces two characters. At
  ~6 KB — three orders of magnitude under the upload limit, a genuine PDF that passes
  every check before this one — the cost doubles per nesting level: seconds at depth 20,
  an hour at depth 30. Any authenticated user could hold a worker slot indefinitely.

The deadline is checked between pages, which bounds every multi-page case. A *single*
page that never returns is outside this module's reach — control is inside MuPDF — and is
bounded by Celery's soft time limit, which is why `SoftTimeLimitExceeded` is re-raised
here rather than swallowed by the parser-failure handlers.

Memory is bounded outside this module and imperfectly: `worker_max_memory_per_child`
recycles a child *after* a task completes, so it does not stop one task allocating
several gigabytes. The container limit is what stops that, at the cost of the child. See
`worker/celery_app.py`.
"""

import time
from dataclasses import dataclass

import pymupdf
from celery.exceptions import SoftTimeLimitExceeded

#: Pages read at most. Beyond this the read is marked truncated rather than abandoned:
#: a long document is still worth what its first pages say, and M8 will know it was
#: bounded.
MAX_PAGES = 40

#: Characters kept at most, across all pages.
MAX_CHARACTERS = 200_000

#: How long the read may take, in seconds, before it gives up and reports what it has.
#:
#: Comfortably longer than any honest document takes and far shorter than the Celery soft
#: time limit, so an ordinary slow file is read while a hostile one is stopped here —
#: with a state to show for it — rather than by the task being killed.
DEADLINE_SECONDS = 20.0


class PasswordProtected(Exception):
    """The document needs a password. Terminal: no retry produces one."""


class UnreadableDocument(Exception):
    """The parser could not open or read the file. Terminal for the same reason."""


class ReadTookTooLong(Exception):
    """The read exceeded its deadline. Terminal, and deliberately so: a document that
    exhausted the bound once will exhaust it again, and retrying it automatically is
    three more chances to occupy a worker. The user may still ask for it deliberately."""


@dataclass(frozen=True)
class ExtractedText:
    #: The document's own page count, which may exceed `pages_read`.
    page_count: int
    #: How many pages were actually looked at. Distinct from `page_count`, because a cap
    #: can stop the read early and a reader who assumes they match will describe a
    #: partial reading as a complete one.
    pages_read: int
    character_count: int
    content: str
    truncated: bool
    #: Whether any page yielded actual characters.
    #:
    #: Computed from the pages rather than from `len(content)`, and this is not
    #: pedantry. Joining N empty pages with newlines gives a string of length N-1, so a
    #: three-page scan produced `character_count == 2`, `has_text_layer == True`, and a
    #: user was shown **"Read — the text has been read"** for a document from which
    #: nothing was read. Whitespace is stripped for the same reason: a page containing
    #: only a space is a page with no text on it.
    has_text_layer: bool


def extract(content: bytes) -> ExtractedText:
    """Read the native text layer, bounded.

    Takes bytes rather than a path or a key: this module has no business knowing where a
    document is stored, and a function that cannot reach the object store cannot be the
    thing that leaks one.
    """
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except SoftTimeLimitExceeded:
        # Must pass through. It derives from `Exception`, so the broad handler below
        # caught Celery's own deadline and reported the file as corrupt — telling the
        # user a false thing about their document, and letting the task carry on writing
        # past the moment it was told to stop.
        raise
    except Exception as exc:
        raise UnreadableDocument(type(exc).__name__) from exc

    try:
        if document.needs_pass:
            # Checked before any page is touched. An encrypted document's page objects
            # are not readable anyway, and asking for them first turns a clean answer
            # into a parser error.
            raise PasswordProtected()

        total_pages = document.page_count
        if total_pages == 0:
            # It opened and has no pages: a truncated or structurally broken file.
            # Letting this fall through to the zero-length reading would call it a scan,
            # telling the user their perfectly good photograph could not be read when
            # what they actually have is a damaged file.
            raise UnreadableDocument("no pages")

        pages: list[str] = []
        characters = 0
        truncated = total_pages > MAX_PAGES

        for index in range(min(total_pages, MAX_PAGES)):
            if time.monotonic() > deadline:
                # The work bound. A page cap limits how much text comes *out*, not what
                # it costs to get: nested Form XObjects cost exponential time inside one
                # `get_text()` while producing almost nothing, at a few kilobytes. What
                # was read is kept — a long document is worth its first pages — and
                # `truncated` says the reading is partial.
                truncated = True
                break
            try:
                text = document.load_page(index).get_text()
            except SoftTimeLimitExceeded:
                raise
            except Exception as exc:
                # A page this parser cannot read makes the document unreadable. Salvaging
                # the good pages is a defensible design and is not the one implemented:
                # returning a partial reading with no record of which pages were skipped
                # would let M8 draw a conclusion from a document with a hole in it and no
                # way to know. If that is ever revisited, the missing pages have to be
                # recorded on the row rather than silently dropped.
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

        return ExtractedText(
            page_count=total_pages,
            pages_read=len(pages),
            # The characters that came out of the pages, not the length of the joined
            # string — see `has_text_layer`.
            character_count=characters,
            content="\n".join(pages),
            truncated=truncated,
            has_text_layer=any(page.strip() for page in pages),
        )
    except (PasswordProtected, UnreadableDocument, SoftTimeLimitExceeded):
        raise
    except Exception as exc:
        # Everything else becomes a failure code. `needs_pass` and `page_count` are parser
        # calls too, and an error from either used to propagate raw — leaving the run
        # RUNNING and the document stuck in `EXTRACTING_TEXT`, a state that is neither
        # terminal nor retryable, with no user or system recovery. `type(exc).__name__`
        # rather than the message, so a parser string never reaches a log.
        raise UnreadableDocument(type(exc).__name__) from exc
    finally:
        # Always closed, including on the password and unreadable paths: PyMuPDF holds
        # the whole stream, and a worker that leaks one document per hostile upload is a
        # worker that eventually stops.
        document.close()
