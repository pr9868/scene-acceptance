"""Bounded native PDF page/region intake with source provenance, without OCR."""

from pathlib import Path
import io
import math
from contextlib import closing

from .model import ContractError, digest_bytes, sha
from .review.schemas import obj, SOURCE_LOCATION

REGION = {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4}
LOCATION = SOURCE_LOCATION
SELECTION = obj(
    {"page": {"type": "integer", "minimum": 1}, "region_pdf_points": REGION}
)
SELECTION["required"] = ["page"]


def extract(
    source: str | Path, selections: list[dict], caption: str, source_path: str
) -> list[dict]:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise ContractError("PDF briefs require scene-acceptance[pdf]") from exc
    source = Path(source)
    if source.stat().st_size > 33554432:
        raise ContractError("PDF exceeds 32 MiB")
    if not 1 <= len(selections) <= 12:
        raise ContractError("Select one to twelve PDF page regions")
    digest = sha(source)
    rows = []
    seen = set()
    total = 0
    try:
        with pdfium.PdfDocument(source) as document:
            if len(document) > 1000:
                raise ContractError("PDF exceeds 1,000-page document budget")
            for index, selection in enumerate(selections):
                number = selection["page"]
                if type(number) is not int or not 1 <= number <= len(document):
                    raise ContractError("Selected PDF page is outside the document")
                with closing(document[number - 1]) as page:
                    if page.get_rotation() != 0:
                        raise ContractError(
                            "Normalize rotated PDF pages before region extraction; provenance must describe the supplied revision"
                        )
                    bounds = list(page.get_bbox())
                    region = selection.get("region_pdf_points", bounds)
                    x0, y0, x1, y1 = region
                    if (
                        not all(math.isfinite(v) for v in region)
                        or x0 >= x1
                        or y0 >= y1
                        or x0 < bounds[0]
                        or y0 < bounds[1]
                        or x1 > bounds[2]
                        or y1 > bounds[3]
                    ):
                        raise ContractError(
                            "PDF region must lie inside the selected page"
                        )
                    identity = (number, *region)
                    if identity in seen:
                        raise ContractError("Duplicate PDF page region")
                    seen.add(identity)
                    width, height = page.get_size()
                    scale = min(2.0, 2048 / max(width, height))
                    if (
                        width <= 0
                        or height <= 0
                        or width * height * scale * scale > 16000000
                    ):
                        raise ContractError("PDF rendering exceeds pixel budget")
                    with closing(page.get_textpage()) as textpage:
                        if textpage.count_chars() > 262144:
                            raise ContractError("PDF page exceeds text budget")
                        text = textpage.get_text_bounded(
                            left=x0, bottom=y0, right=x1, top=y1, errors="strict"
                        ).replace("\r\n", "\n")
                    if len(text.encode("utf-8")) > 65536:
                        raise ContractError("PDF region text exceeds 64 KiB")
                    bitmap = page.render(scale=scale)
                    try:
                        image = bitmap.to_pil().convert("RGB")
                        crop = (
                            math.floor((x0 - bounds[0]) * scale),
                            math.floor((bounds[3] - y1) * scale),
                            math.ceil((x1 - bounds[0]) * scale),
                            math.ceil((bounds[3] - y0) * scale),
                        )
                        image = image.crop(crop)
                        stream = io.BytesIO()
                        image.save(stream, format="PNG")
                        pixels = stream.getvalue()
                    finally:
                        bitmap.close()
                    total += len(pixels)
                    if len(pixels) > 8388608 or total > 33554432:
                        raise ContractError(
                            "PDF page images exceed evidence byte budget"
                        )
                    location = dict(
                        document_path=source_path,
                        document_sha256=digest,
                        page=number,
                        region_pdf_points=region,
                        coordinates="PDF points; origin bottom left",
                    )
                    name = f"pdf-{digest[:16]}-{index:02d}"
                    label = f"{caption}, page {number}, region {region}"
                    if text:
                        data = text.encode("utf-8")
                        rows.append(
                            dict(
                                path=name + ".txt",
                                role="text",
                                caption=label,
                                text=text,
                                sha256=digest_bytes(data),
                                source_location=dict(
                                    location, extraction="embedded_text"
                                ),
                                _bytes=data,
                            )
                        )
                    rows.append(
                        dict(
                            path=name + ".png",
                            role="reference_image",
                            caption=label,
                            sha256=digest_bytes(pixels),
                            source_location=dict(
                                location, extraction="rendered_page_region"
                            ),
                            _bytes=pixels,
                            width=image.width,
                            height=image.height,
                            mode="RGB",
                            mime="image/png",
                        )
                    )
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError("PDF could not be decoded: " + str(exc)) from exc
    if sha(source) != digest:
        raise ContractError("PDF changed during extraction")
    return rows
