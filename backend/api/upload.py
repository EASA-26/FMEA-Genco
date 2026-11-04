"""Read one uploaded file from a multipart/form-data request, in memory.

Starlette's built-in form parsing spools large files to a temporary file on
disk and only checks sizes after the whole body has arrived. Uploads here must
never touch disk and must be rejected as soon as they grow too large, so the
request body is streamed through python-multipart's low-level parser instead:

* ``Content-Length`` (when sent) gives an early 413, but is never relied on;
  the bytes actually received are counted as they arrive.
* The file part is collected into memory and stops at ``max_bytes``.
* The file name's extension is checked as soon as the part headers arrive.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Iterable, Mapping
from dataclasses import dataclass

from python_multipart.exceptions import FormParserError
from python_multipart.multipart import MultipartParser, parse_options_header
from starlette.requests import ClientDisconnect

# Allowance for multipart boundaries, part headers and small extra form fields.
BODY_OVERHEAD_BYTES = 1024 * 1024


class UploadRejected(Exception):
    """The upload cannot be used; ``message`` is shown to the engineer."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class ReceivedFile:
    filename: str
    data: bytes


def wrong_type_message(extensions: Iterable[str]) -> str:
    listed = " or ".join(extensions)
    return f"Please upload an Excel workbook ({listed})."


def too_large_message(max_bytes: int) -> str:
    megabytes = max_bytes / (1024 * 1024)
    size = f"{megabytes:g} MB" if megabytes >= 1 else f"{max_bytes // 1024} KB"
    return f"The file is larger than {size}. Please upload a smaller workbook."


MSG_NO_FILE = "No file was received. Please choose an Excel workbook and try again."
MSG_INCOMPLETE = "The upload did not finish. Please try again."


def clean_filename(raw: str) -> str:
    """Just the file name: no folders, control characters or surrounding spaces."""
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ord(ch) >= 32 and ord(ch) != 127)
    return name.strip()[:255]


def has_accepted_extension(filename: str, extensions: Iterable[str]) -> bool:
    lowered = filename.lower()
    return any(lowered.endswith(ext.lower()) and len(lowered) > len(ext) for ext in extensions)


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


class _SingleFileCollector:
    """python-multipart callbacks that keep only the wanted file part."""

    def __init__(self, field_name: str, max_bytes: int, extensions: tuple[str, ...]) -> None:
        self.field_name = field_name
        self.max_bytes = max_bytes
        self.extensions = extensions
        self.filename: str | None = None
        self.buffer = bytearray()
        self.finished = False
        # Set when the file has the wrong extension: the rest of the body is
        # read and discarded so the browser reliably receives the 400 reply.
        self.rejection: UploadRejected | None = None
        self._header_name = bytearray()
        self._header_value = bytearray()
        self._disposition = b""
        self._collecting = False
        self._found = False

    def callbacks(self) -> dict:
        return {
            "on_part_begin": self.on_part_begin,
            "on_header_field": self.on_header_field,
            "on_header_value": self.on_header_value,
            "on_header_end": self.on_header_end,
            "on_headers_finished": self.on_headers_finished,
            "on_part_data": self.on_part_data,
            "on_part_end": self.on_part_end,
        }

    def on_part_begin(self) -> None:
        self._disposition = b""
        self._collecting = False

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_name += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]

    def on_header_end(self) -> None:
        if bytes(self._header_name).strip().lower() == b"content-disposition":
            self._disposition = bytes(self._header_value)
        self._header_name.clear()
        self._header_value.clear()

    def on_headers_finished(self) -> None:
        _, options = parse_options_header(self._disposition)
        if self._found or _decode(options.get(b"name", b"")) != self.field_name:
            return  # another form field, or a second file: ignored
        filename = clean_filename(_decode(options.get(b"filename", b"")))
        if not filename:
            return  # a plain field, or a browser form sent with no file chosen
        self._found = True
        self.filename = filename
        if not has_accepted_extension(self.filename, self.extensions):
            self.rejection = UploadRejected(400, wrong_type_message(self.extensions))
            return
        self._collecting = True

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if not self._collecting:
            return
        if len(self.buffer) + (end - start) > self.max_bytes:
            raise UploadRejected(413, too_large_message(self.max_bytes))
        self.buffer += data[start:end]

    def on_part_end(self) -> None:
        if self._collecting:
            self._collecting = False
            self.finished = True


async def read_single_file(
    headers: Mapping[str, str],
    stream: AsyncIterator[bytes],
    *,
    field_name: str,
    max_bytes: int,
    extensions: tuple[str, ...],
) -> ReceivedFile:
    """Collect the file sent in form field ``field_name``.

    ``headers`` is the request's header mapping and ``stream`` its body chunks
    (``request.stream()``). Raises `UploadRejected` with the status and message
    to return.
    """
    content_type = headers.get("content-type") or ""
    media_type, params = parse_options_header(content_type)
    boundary = params.get(b"boundary")
    if media_type != b"multipart/form-data" or not boundary:
        raise UploadRejected(400, MSG_NO_FILE)

    body_limit = max_bytes + BODY_OVERHEAD_BYTES
    declared = (headers.get("content-length") or "").strip()
    if declared.isdigit() and int(declared) > body_limit:
        raise UploadRejected(413, too_large_message(max_bytes))

    collector = _SingleFileCollector(field_name, max_bytes, extensions)
    try:
        parser = MultipartParser(boundary, collector.callbacks())
    except (FormParserError, ValueError):
        raise UploadRejected(400, MSG_NO_FILE) from None

    received = 0
    try:
        async for chunk in stream:
            if not chunk:
                continue
            received += len(chunk)
            if received > body_limit:
                if collector.rejection is not None:
                    raise collector.rejection
                raise UploadRejected(413, too_large_message(max_bytes))
            parser.write(chunk)
        parser.finalize()
    except ClientDisconnect:
        raise UploadRejected(400, MSG_INCOMPLETE) from None
    except FormParserError:
        if collector.rejection is not None:
            raise collector.rejection from None
        raise UploadRejected(400, MSG_INCOMPLETE if collector.filename else MSG_NO_FILE) from None

    if collector.rejection is not None:
        raise collector.rejection
    if collector.filename is None:
        raise UploadRejected(400, MSG_NO_FILE)
    if not collector.finished:
        raise UploadRejected(400, MSG_INCOMPLETE)
    return ReceivedFile(filename=collector.filename, data=bytes(collector.buffer))
