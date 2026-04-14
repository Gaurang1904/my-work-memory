from collections.abc import Iterable


def chunk_text(
    page_map: Iterable[dict],
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict]:
    chunks: list[dict] = []
    chunk_index = 0

    for page in page_map:
        text = page["text"].strip()
        if not text:
            continue

        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    {
                        "chunk_index": chunk_index,
                        "chunk_text": chunk_text,
                        "page_number": page.get("page_number"),
                        "section_title": None,
                    }
                )
                chunk_index += 1

            if end >= len(text):
                break
            start = max(end - chunk_overlap, start + 1)

    return chunks

