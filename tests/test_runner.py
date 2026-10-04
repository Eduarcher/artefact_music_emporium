from emporium.agent.runner import _extract_text


def test_extract_text_passes_through_plain_string() -> None:
    assert _extract_text("algum texto") == "algum texto"


def test_extract_text_unwraps_content_blocks() -> None:
    content = [
        {"type": "text", "text": '{"products": []}', "id": "lc_1"},
        {"type": "text", "text": "mais texto"},
    ]
    assert _extract_text(content) == '{"products": []}\nmais texto'


def test_extract_text_ignores_non_text_blocks() -> None:
    content = [{"type": "image", "data": "bytes"}, {"type": "text", "text": "ok"}]
    assert _extract_text(content) == "{'type': 'image', 'data': 'bytes'}\nok"


def test_extract_text_serializes_dict_content() -> None:
    assert _extract_text({"error": "not found"}) == '{"error": "not found"}'
