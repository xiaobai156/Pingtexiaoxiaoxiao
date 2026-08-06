from __future__ import annotations

from io import BytesIO

from pingte.domain.zodiac import ZODIACS


IMAGE_TEMPLATE_CACHE: dict[tuple[str, str, int, tuple[int, int]], object] = {}


def decode_label_image(data: bytes) -> bytes | None:
    if data.startswith((b"\x89PNG", b"\xff\xd8\xff")):
        return data
    if len(data) <= 8:
        return None
    decoded = bytearray(data)
    key = decoded[:8]
    for index in range(8, len(decoded)):
        decoded[index] ^= key[(index - 8) % 8]
    image_data = bytes(decoded[8:])
    if image_data.startswith((b"\x89PNG", b"\xff\xd8\xff")):
        return image_data
    return None


def image_component_rows(
    mask,
    cv2,
    *,
    minimum_area: int,
    kernel_size: tuple[int, int],
    row_tolerance: int,
) -> list[list[list[int]]]:
    dilated = cv2.dilate(
        mask,
        cv2.getStructuringElement(cv2.MORPH_RECT, kernel_size),
        iterations=1,
    )
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        dilated,
        8,
    )
    boxes = sorted(
        [
            [
                int(stats[index][0]),
                int(stats[index][1]),
                int(stats[index][0] + stats[index][2]),
                int(stats[index][1] + stats[index][3]),
                int(stats[index][4]),
            ]
            for index in range(1, count)
            if stats[index][4] > minimum_area
            and stats[index][2] < mask.shape[1] * 0.8
            and stats[index][3] < mask.shape[0] * 0.25
        ],
        key=lambda box: ((box[1] + box[3]) / 2, box[0]),
    )
    rows: list[list[list[int]]] = []
    for box in boxes:
        center_y = (box[1] + box[3]) / 2
        row = next(
            (
                item
                for item in rows
                if abs(
                    center_y
                    - sum((part[1] + part[3]) / 2 for part in item)
                    / len(item)
                )
                <= row_tolerance
            ),
            None,
        )
        if row is None:
            rows.append([box])
        else:
            row.append(box)
    return [sorted(row) for row in rows]


def red_component_rows(mask, cv2) -> list[list[list[int]]]:
    return image_component_rows(
        mask,
        cv2,
        minimum_area=20,
        kernel_size=(3, 3),
        row_tolerance=14,
    )


def extract_red_issue_zodiac_from_encrypted_image(
    data: bytes,
    issue: str,
) -> str | None:
    image_data = decode_label_image(data)
    if not image_data:
        return None
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None

    image = Image.open(BytesIO(image_data)).convert("RGB")
    pixels = np.array(image)
    red_mask = (
        (pixels[:, :, 0] > 180)
        & (pixels[:, :, 1] < 120)
        & (pixels[:, :, 2] < 120)
    ).astype("uint8") * 255
    candidates: list[str] = []
    issue_labels = (f"{int(issue)}期：", f"{int(issue)}期:")
    for row in red_component_rows(red_mask, cv2):
        groups = merge_close_boxes(row)
        if len(groups) < 2:
            continue
        prefix_crop = crop_mask(red_mask, groups[:-1])
        prefix_score = max(
            rendered_text_score(
                prefix_crop,
                label,
                Image,
                ImageDraw,
                ImageFont,
                cv2,
                np,
            )
            for label in issue_labels
        )
        if prefix_score < 0.72:
            continue
        zodiac_crop = crop_mask(red_mask, [groups[-1]])
        zodiac = match_zodiac_crop(
            zodiac_crop,
            Image,
            ImageDraw,
            ImageFont,
            cv2,
            np,
        )
        if zodiac:
            candidates.append(zodiac)
    distinct = list(dict.fromkeys(candidates))
    return distinct[0] if len(distinct) == 1 else None


def first_image_row_colon_end(
    row: list[list[int]],
    image_width: int,
) -> int | None:
    dots = [
        box
        for box in row
        if box[2] - box[0] <= 8
        and box[3] - box[1] <= 10
        and box[0] < image_width * 0.25
    ]
    pairs = [
        (first, second)
        for first in dots
        for second in dots
        if first is not second
        and abs(first[0] - second[0]) <= 2
        and abs(first[2] - second[2]) <= 2
        and abs(
            (first[1] + first[3]) / 2
            - (second[1] + second[3]) / 2
        )
        >= 5
    ]
    if not pairs:
        return None
    first, second = min(
        pairs,
        key=lambda pair: min(pair[0][0], pair[1][0]),
    )
    return max(first[2], second[2])


def image_prefix_matches_issue(
    crop,
    issue: str,
    Image,
    ImageDraw,
    ImageFont,
    cv2,
    np,
) -> bool:
    requested = int(issue)
    scores = {}
    for candidate in range(
        max(1, requested - 10),
        min(999, requested + 10) + 1,
    ):
        scores[candidate] = max(
            rendered_text_score(
                crop,
                f"{candidate}期:",
                Image,
                ImageDraw,
                ImageFont,
                cv2,
                np,
            ),
            rendered_text_score(
                crop,
                f"{candidate}期：",
                Image,
                ImageDraw,
                ImageFont,
                cv2,
                np,
            ),
        )
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    requested_score = scores.get(requested, 0.0)
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    return bool(
        ranked
        and ranked[0][0] == requested
        and requested_score >= 0.70
        and requested_score - second_score >= 0.01
    )


def extract_historical_issue_zodiac_from_image(
    data: bytes,
    issue: str,
) -> str | None:
    image_data = decode_label_image(data)
    if not image_data:
        return None
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None

    image = Image.open(BytesIO(image_data)).convert("RGB")
    pixels = np.array(image)
    dark_mask = (pixels.min(axis=2) < 130).astype("uint8") * 255
    candidates: list[str] = []
    rows = image_component_rows(
        dark_mask,
        cv2,
        minimum_area=10,
        kernel_size=(2, 2),
        row_tolerance=10,
    )
    for row in rows:
        if min(box[0] for box in row) > dark_mask.shape[1] * 0.03:
            continue
        colon_end = first_image_row_colon_end(row, dark_mask.shape[1])
        if colon_end is None:
            continue
        prefix_boxes = [
            box
            for box in row
            if box[0] < colon_end and box[2] <= colon_end
        ]
        prefix_crop = crop_mask(dark_mask, prefix_boxes)
        if not prefix_crop.size or not image_prefix_matches_issue(
            prefix_crop,
            issue,
            Image,
            ImageDraw,
            ImageFont,
            cv2,
            np,
        ):
            continue
        row_zodiacs = []
        for box in row:
            width = box[2] - box[0]
            height = box[3] - box[1]
            if box[0] <= dark_mask.shape[1] * 0.72 or not (
                12 <= width <= 35 and 15 <= height <= 35
            ):
                continue
            zodiac = match_zodiac_crop(
                crop_mask(dark_mask, [box]),
                Image,
                ImageDraw,
                ImageFont,
                cv2,
                np,
            )
            if zodiac:
                row_zodiacs.append(zodiac)
        distinct_row = list(dict.fromkeys(row_zodiacs))
        if len(distinct_row) != 1:
            return None
        candidates.append(distinct_row[0])
    distinct = list(dict.fromkeys(candidates))
    return distinct[0] if len(distinct) == 1 else None


def extract_issue_zodiac_from_label_image(
    data: bytes,
    issue: str,
) -> str | None:
    return (
        extract_red_issue_zodiac_from_encrypted_image(data, issue)
        or extract_historical_issue_zodiac_from_image(data, issue)
    )


def crop_mask(mask, boxes):
    if not boxes:
        return mask[0:0, 0:0]
    x0 = max(0, min(box[0] for box in boxes) - 3)
    y0 = max(0, min(box[1] for box in boxes) - 3)
    x1 = min(mask.shape[1], max(box[2] for box in boxes) + 3)
    y1 = min(mask.shape[0], max(box[3] for box in boxes) + 3)
    return mask[y0:y1, x0:x1]


def font_paths() -> list[str]:
    return [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ]


def rendered_text_score(
    crop,
    text: str,
    Image,
    ImageDraw,
    ImageFont,
    cv2,
    np,
) -> float:
    crop = cv2.resize(crop, (160, 70), interpolation=cv2.INTER_AREA)
    best = 0.0
    for font_path in font_paths():
        for size in range(22, 42, 2):
            try:
                template = cached_render_template(
                    text,
                    font_path,
                    size,
                    Image,
                    ImageDraw,
                    ImageFont,
                    cv2,
                    np,
                    (160, 70),
                )
            except OSError:
                continue
            score = float(
                cv2.matchTemplate(
                    crop,
                    template,
                    cv2.TM_CCOEFF_NORMED,
                )[0][0]
            )
            best = max(best, score)
    return best


def match_zodiac_crop(crop, Image, ImageDraw, ImageFont, cv2, np) -> str | None:
    if not crop.size:
        return None
    crop = cv2.resize(crop, (80, 80), interpolation=cv2.INTER_AREA)
    best_score = 0.0
    best_zodiac = ""
    for font_path in font_paths():
        for size in range(24, 54, 2):
            for zodiac in ZODIACS:
                try:
                    template = cached_render_template(
                        zodiac,
                        font_path,
                        size,
                        Image,
                        ImageDraw,
                        ImageFont,
                        cv2,
                        np,
                        (80, 80),
                    )
                except OSError:
                    continue
                score = float(
                    cv2.matchTemplate(
                        crop,
                        template,
                        cv2.TM_CCOEFF_NORMED,
                    )[0][0]
                )
                if score > best_score:
                    best_score = score
                    best_zodiac = zodiac
    return best_zodiac if best_score >= 0.65 else None


def cached_render_template(
    text: str,
    font_path: str,
    font_size: int,
    Image,
    ImageDraw,
    ImageFont,
    cv2,
    np,
    output_size: tuple[int, int],
):
    key = (text, font_path, font_size, output_size)
    template = IMAGE_TEMPLATE_CACHE.get(key)
    if template is None:
        font = ImageFont.truetype(font_path, font_size)
        template = render_template(
            text,
            font,
            Image,
            ImageDraw,
            cv2,
            np,
            output_size,
        )
        IMAGE_TEMPLATE_CACHE[key] = template
    return template


def merge_close_boxes(boxes: list[list[int]]) -> list[list[int]]:
    merged: list[list[int]] = []
    for box in boxes:
        if not merged or box[0] - merged[-1][2] > 6:
            merged.append(box[:])
            continue
        merged[-1][0] = min(merged[-1][0], box[0])
        merged[-1][1] = min(merged[-1][1], box[1])
        merged[-1][2] = max(merged[-1][2], box[2])
        merged[-1][3] = max(merged[-1][3], box[3])
        merged[-1][4] += box[4]
    return merged


def bottom_line_boxes(boxes: list[list[int]]) -> list[list[int]]:
    if not boxes:
        return []
    max_center_y = max((box[1] + box[3]) / 2 for box in boxes)
    return [
        box
        for box in boxes
        if (box[1] + box[3]) / 2 >= max_center_y - 25
    ]


def render_template(
    text: str,
    font,
    Image,
    ImageDraw,
    cv2,
    np,
    size: tuple[int, int],
):
    canvas = Image.new("L", (240, 120), 0)
    draw = ImageDraw.Draw(canvas)
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text(
        (
            (240 - (bbox[2] - bbox[0])) // 2 - bbox[0],
            (120 - (bbox[3] - bbox[1])) // 2 - bbox[1],
        ),
        text,
        font=font,
        fill=255,
    )
    template = np.array(canvas)
    points = cv2.findNonZero(template)
    if points is None:
        return cv2.resize(template, size, interpolation=cv2.INTER_AREA)
    x, y, width, height = cv2.boundingRect(points)
    template = template[
        max(0, y - 3) : y + height + 3,
        max(0, x - 3) : x + width + 3,
    ]
    return cv2.resize(template, size, interpolation=cv2.INTER_AREA)
