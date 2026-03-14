from typing import List


def split_message(text: str, max_length: int = 2800) -> List[str]:
    """Splits text into chunks no longer than max_length."""
    if max_length <= 0:
        raise ValueError("max_length must be positive")

    if len(text) <= max_length:
        return [text]

    chunks: List[str] = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + max_length, text_length)

        if end < text_length:
            split_at = max(
                text.rfind("\n", start, end),
                text.rfind(" ", start, end)
            )
            if split_at > start:
                end = split_at + 1

        chunk = text[start:end].rstrip()
        if not chunk:
            chunk = text[start:min(start + max_length, text_length)]
            end = start + len(chunk)

        chunks.append(chunk)
        start = end

        while start < text_length and text[start].isspace():
            start += 1

    return chunks
