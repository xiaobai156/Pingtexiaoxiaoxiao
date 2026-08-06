from pingte.parse.custom.image_result import decode_label_image


def test_image_parser_accepts_plain_png_and_reverses_eight_byte_xor_wrapper():
    plain = b"\x89PNG\r\n\x1a\nimage-body"
    key = b"12345678"
    encrypted = key + bytes(
        value ^ key[index % len(key)]
        for index, value in enumerate(plain)
    )

    assert decode_label_image(plain) == plain
    assert decode_label_image(encrypted) == plain


def test_image_parser_rejects_non_image_payload():
    assert decode_label_image(b"short") is None
    assert decode_label_image(b"12345678not-an-image") is None
