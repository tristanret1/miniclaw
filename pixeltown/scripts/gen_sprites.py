#!/usr/bin/env python3
"""Generate pixel art character spritesheets with walk/idle animations.

Each sheet: 39 frames × 32×32px = 1248×32 PNG
Frame layout matches NoobSprite.png:
  0-2:   walk down (3 frames)
  3-5:   walk down alt
  6-8:   walk down alt2
  9-11:  walk up (3 frames)
  12-14: walk right (3 frames)
  15-17: walk right alt
  18-20: walk left (3 frames)
  21-33: unused (transparent)
  34:    idle right
  35:    idle down
  36:    idle left
  37:    idle up
  38:    unused

Usage:
  python scripts/gen_sprites.py
"""

from PIL import Image, ImageDraw
from pathlib import Path
import random

OUT_DIR = Path(__file__).parent.parent / "pixeltown" / "public" / "sprites"
FRAME = 32
TOTAL_FRAMES = 39

# ── Character definitions ──

CHARACTERS = [
    {
        "name": "Mage",
        "skin": (255, 220, 180),
        "hair": (80, 50, 120),      # purple
        "shirt": (100, 60, 160),     # dark purple robe
        "pants": (70, 40, 120),
        "shoes": (60, 30, 80),
        "hat": "pointy",
    },
    {
        "name": "Knight",
        "skin": (240, 200, 160),
        "hair": (60, 60, 60),        # dark gray
        "shirt": (140, 150, 160),    # silver armor
        "pants": (100, 110, 120),
        "shoes": (80, 80, 90),
        "hat": None,
    },
    {
        "name": "Ranger",
        "skin": (220, 180, 140),
        "hair": (140, 90, 40),       # brown
        "shirt": (60, 100, 50),      # forest green
        "pants": (80, 70, 50),
        "shoes": (90, 70, 40),
        "hat": "hood",
    },
    {
        "name": "Scholar",
        "skin": (255, 230, 200),
        "hair": (200, 170, 100),     # blonde
        "shirt": (50, 80, 140),      # blue
        "pants": (40, 40, 80),
        "shoes": (80, 60, 40),
        "hat": None,
    },
    {
        "name": "Merchant",
        "skin": (200, 160, 120),
        "hair": (40, 30, 20),        # black
        "shirt": (180, 140, 60),     # gold tunic
        "pants": (120, 90, 40),
        "shoes": (100, 70, 30),
        "hat": "beret",
    },
    {
        "name": "Witch",
        "skin": (240, 210, 190),
        "hair": (180, 40, 60),       # red
        "shirt": (30, 30, 30),       # black robe
        "pants": (40, 40, 40),
        "shoes": (50, 30, 50),
        "hat": "pointy",
    },
    {
        "name": "Farmer",
        "skin": (230, 190, 150),
        "hair": (100, 70, 30),       # brown
        "shirt": (200, 100, 60),     # orange overalls
        "pants": (80, 100, 140),     # denim
        "shoes": (100, 80, 50),
        "hat": "straw",
    },
    {
        "name": "Pirate",
        "skin": (210, 170, 130),
        "hair": (20, 20, 20),        # black
        "shirt": (160, 40, 40),      # red
        "pants": (50, 50, 50),
        "shoes": (70, 50, 30),
        "hat": "bandana",
    },
    {
        "name": "Priestess",
        "skin": (255, 225, 195),
        "hair": (180, 130, 60),      # golden brown long hair
        "shirt": (240, 240, 250),    # white robe
        "pants": (220, 220, 235),
        "shoes": (180, 160, 140),
        "hat": "longhair",
        "female": True,
    },
    {
        "name": "Fairy",
        "skin": (255, 230, 210),
        "hair": (220, 160, 200),     # pink long hair
        "shirt": (150, 220, 180),    # mint green dress
        "pants": (130, 200, 160),
        "shoes": (160, 140, 120),
        "hat": "longhair",
        "female": True,
    },
    {
        "name": "Archer",
        "skin": (235, 200, 170),
        "hair": (60, 40, 30),        # dark brown long hair
        "shirt": (140, 80, 50),      # leather
        "pants": (100, 70, 40),
        "shoes": (80, 60, 30),
        "hat": "ponytail",
        "female": True,
    },
]


def darken(color, factor=0.7):
    return tuple(max(0, int(c * factor)) for c in color)


def lighten(color, factor=1.3):
    return tuple(min(255, int(c * factor)) for c in color)


def draw_character(img, fx, fy, char, direction="down", walk_phase=0):
    """Draw a single character frame at pixel position (fx, fy) within a 32x32 area.

    direction: down/up/left/right
    walk_phase: 0=stand, 1=left foot, 2=right foot
    """
    draw = ImageDraw.Draw(img)
    # Center character in 32x32 frame
    cx = fx + 16  # center x
    by = fy + 25  # bottom y (feet)

    skin = char["skin"]
    hair = char["hair"]
    shirt = char["shirt"]
    pants = char["pants"]
    shoes = char["shoes"]

    skin_dark = darken(skin, 0.85)
    shirt_dark = darken(shirt, 0.7)
    hair_dark = darken(hair, 0.7)

    # Walk bob offset
    bob = -1 if walk_phase in (1, 2) else 0

    # ── Shoes ──
    if walk_phase == 1:
        draw.rectangle([cx - 4, by - 2, cx - 2, by], fill=shoes)
        draw.rectangle([cx + 1, by - 3, cx + 3, by - 1], fill=shoes)
    elif walk_phase == 2:
        draw.rectangle([cx - 4, by - 3, cx - 2, by - 1], fill=shoes)
        draw.rectangle([cx + 1, by - 2, cx + 3, by], fill=shoes)
    else:
        draw.rectangle([cx - 4, by - 2, cx - 2, by], fill=shoes)
        draw.rectangle([cx + 1, by - 2, cx + 3, by], fill=shoes)

    # ── Legs ──
    is_female = char.get("female", False)
    leg_top = by - 6
    if walk_phase == 1:
        draw.rectangle([cx - 4, leg_top + bob, cx - 2, by - 2], fill=pants)
        draw.rectangle([cx + 1, leg_top - 1 + bob, cx + 3, by - 3], fill=pants)
    elif walk_phase == 2:
        draw.rectangle([cx - 4, leg_top - 1 + bob, cx - 2, by - 3], fill=pants)
        draw.rectangle([cx + 1, leg_top + bob, cx + 3, by - 2], fill=pants)
    else:
        draw.rectangle([cx - 4, leg_top + bob, cx - 2, by - 2], fill=pants)
        draw.rectangle([cx + 1, leg_top + bob, cx + 3, by - 2], fill=pants)

    # ── Body / torso ──
    body_top = by - 13 + bob
    body_bot = leg_top + bob
    draw.rectangle([cx - 5, body_top, cx + 4, body_bot], fill=shirt)
    # Shirt detail
    draw.rectangle([cx - 5, body_top, cx + 4, body_top + 1], fill=shirt_dark)

    # ── Skirt (female characters) ──
    if is_female:
        skirt_color = shirt
        skirt_dark = shirt_dark
        skirt_top = body_bot - 1
        skirt_bot = leg_top + 3 + bob
        # Flared skirt shape
        draw.rectangle([cx - 6, skirt_top, cx + 5, skirt_bot], fill=skirt_color)
        draw.rectangle([cx - 6, skirt_bot, cx + 5, skirt_bot], fill=skirt_dark)

    # ── Arms ──
    if direction in ("down", "up"):
        # Both arms visible
        arm_swing = 1 if walk_phase == 1 else (-1 if walk_phase == 2 else 0)
        draw.rectangle([cx - 7, body_top + 2 + arm_swing, cx - 5, body_top + 8 + arm_swing], fill=shirt)
        draw.rectangle([cx + 5, body_top + 2 - arm_swing, cx + 7, body_top + 8 - arm_swing], fill=shirt)
        # Hands
        draw.rectangle([cx - 7, body_top + 8 + arm_swing, cx - 5, body_top + 10 + arm_swing], fill=skin)
        draw.rectangle([cx + 5, body_top + 8 - arm_swing, cx + 7, body_top + 10 - arm_swing], fill=skin)
    elif direction == "right":
        arm_swing = 2 if walk_phase == 1 else (-2 if walk_phase == 2 else 0)
        draw.rectangle([cx + 3, body_top + 2 + arm_swing, cx + 5, body_top + 9 + arm_swing], fill=shirt)
        draw.rectangle([cx + 3, body_top + 9 + arm_swing, cx + 5, body_top + 11 + arm_swing], fill=skin)
    else:  # left
        arm_swing = 2 if walk_phase == 1 else (-2 if walk_phase == 2 else 0)
        draw.rectangle([cx - 5, body_top + 2 + arm_swing, cx - 3, body_top + 9 + arm_swing], fill=shirt)
        draw.rectangle([cx - 5, body_top + 9 + arm_swing, cx - 3, body_top + 11 + arm_swing], fill=skin)

    # ── Head ──
    head_top = body_top - 8
    head_bot = body_top
    draw.rectangle([cx - 4, head_top, cx + 3, head_bot], fill=skin)
    # Outline
    draw.rectangle([cx - 5, head_top + 1, cx - 5, head_bot - 1], fill=skin_dark)
    draw.rectangle([cx + 4, head_top + 1, cx + 4, head_bot - 1], fill=skin_dark)

    # ── Hair ──
    hat = char.get("hat")
    if hat == "pointy":
        # Wizard/witch hat
        draw.rectangle([cx - 5, head_top - 1, cx + 4, head_top + 2], fill=hair)
        draw.rectangle([cx - 3, head_top - 3, cx + 2, head_top], fill=hair)
        draw.rectangle([cx - 1, head_top - 5, cx + 1, head_top - 2], fill=hair)
        # Brim
        draw.rectangle([cx - 6, head_top + 2, cx + 5, head_top + 3], fill=hair_dark)
    elif hat == "hood":
        draw.rectangle([cx - 5, head_top - 2, cx + 4, head_top + 3], fill=hair)
        draw.rectangle([cx - 6, head_top, cx - 5, head_top + 4], fill=hair)
        draw.rectangle([cx + 4, head_top, cx + 5, head_top + 4], fill=hair)
    elif hat == "straw":
        draw.rectangle([cx - 6, head_top - 1, cx + 5, head_top + 1], fill=(220, 200, 120))
        draw.rectangle([cx - 4, head_top - 2, cx + 3, head_top], fill=(220, 200, 120))
        draw.rectangle([cx - 7, head_top + 1, cx + 6, head_top + 2], fill=(200, 180, 100))
    elif hat == "bandana":
        draw.rectangle([cx - 5, head_top - 1, cx + 4, head_top + 1], fill=(160, 30, 30))
        draw.rectangle([cx + 4, head_top, cx + 6, head_top + 2], fill=(160, 30, 30))  # tail
        # Hair below
        draw.rectangle([cx - 5, head_top + 1, cx + 4, head_top + 3], fill=hair)
    elif hat == "beret":
        draw.rectangle([cx - 4, head_top - 2, cx + 4, head_top], fill=hair)
        draw.rectangle([cx - 5, head_top - 1, cx + 5, head_top + 1], fill=darken(shirt, 0.9))
    elif hat == "longhair":
        # Long flowing hair — top of head
        draw.rectangle([cx - 5, head_top - 1, cx + 4, head_top + 2], fill=hair)
        # Side strands falling past shoulders
        if direction == "down":
            draw.rectangle([cx - 6, head_top, cx - 4, body_top + 6], fill=hair)
            draw.rectangle([cx + 3, head_top, cx + 5, body_top + 6], fill=hair)
            # Inner strands
            draw.rectangle([cx - 5, head_top + 5, cx - 4, body_top + 4], fill=hair_dark)
            draw.rectangle([cx + 3, head_top + 5, cx + 4, body_top + 4], fill=hair_dark)
        elif direction == "up":
            # Back hair — full cascade
            draw.rectangle([cx - 5, head_top, cx + 4, body_top + 5], fill=hair)
            draw.rectangle([cx - 6, head_top + 2, cx - 4, body_top + 4], fill=hair)
            draw.rectangle([cx + 3, head_top + 2, cx + 5, body_top + 4], fill=hair)
            # Highlight
            draw.rectangle([cx - 2, head_top + 2, cx + 1, body_top + 3], fill=hair_dark)
        elif direction == "right":
            draw.rectangle([cx - 5, head_top, cx - 4, body_top + 5], fill=hair)
            draw.rectangle([cx + 3, head_top, cx + 4, head_top + 4], fill=hair)
            # Flowing strand on back side
            draw.rectangle([cx - 6, head_top + 3, cx - 4, body_top + 6], fill=hair)
        else:  # left
            draw.rectangle([cx + 3, head_top, cx + 4, body_top + 5], fill=hair)
            draw.rectangle([cx - 5, head_top, cx - 4, head_top + 4], fill=hair)
            draw.rectangle([cx + 4, head_top + 3, cx + 6, body_top + 6], fill=hair)
    elif hat == "ponytail":
        # Short bangs + ponytail
        draw.rectangle([cx - 5, head_top - 1, cx + 4, head_top + 2], fill=hair)
        if direction != "up":
            draw.rectangle([cx - 5, head_top, cx - 4, head_top + 3], fill=hair)
            draw.rectangle([cx + 3, head_top, cx + 4, head_top + 3], fill=hair)
        # Ponytail in back
        if direction == "up" or direction == "down":
            draw.rectangle([cx - 1, head_top + 1, cx + 1, body_top + 5], fill=hair)
            draw.rectangle([cx, body_top + 5, cx + 1, body_top + 7], fill=hair)
        elif direction == "left":
            draw.rectangle([cx + 4, head_top + 1, cx + 6, head_top + 5], fill=hair)
            draw.rectangle([cx + 5, head_top + 5, cx + 7, head_top + 7], fill=hair)
        else:  # right
            draw.rectangle([cx - 6, head_top + 1, cx - 4, head_top + 5], fill=hair)
            draw.rectangle([cx - 7, head_top + 5, cx - 5, head_top + 7], fill=hair)
    else:
        # Default short hair
        draw.rectangle([cx - 5, head_top - 1, cx + 4, head_top + 2], fill=hair)
        if direction != "up":
            draw.rectangle([cx - 5, head_top, cx - 4, head_top + 4], fill=hair)
            draw.rectangle([cx + 3, head_top, cx + 4, head_top + 4], fill=hair)

    # ── Face ──
    if direction == "down":
        # Eyes
        draw.rectangle([cx - 3, head_top + 3, cx - 2, head_top + 4], fill=(40, 40, 40))
        draw.rectangle([cx + 1, head_top + 3, cx + 2, head_top + 4], fill=(40, 40, 40))
        # Eye shine
        draw.point([cx - 3, head_top + 3], fill=(255, 255, 255))
        draw.point([cx + 1, head_top + 3], fill=(255, 255, 255))
        if is_female:
            # Eyelashes
            draw.point([cx - 3, head_top + 2], fill=(40, 40, 40))
            draw.point([cx + 2, head_top + 2], fill=(40, 40, 40))
            # Blush
            draw.point([cx - 4, head_top + 5], fill=(255, 180, 180))
            draw.point([cx + 3, head_top + 5], fill=(255, 180, 180))
            # Small mouth
            draw.point([cx, head_top + 6], fill=(220, 130, 130))
        else:
            # Mouth
            draw.rectangle([cx - 1, head_top + 6, cx, head_top + 6], fill=darken(skin, 0.7))
    elif direction == "right":
        draw.rectangle([cx + 1, head_top + 3, cx + 2, head_top + 4], fill=(40, 40, 40))
        draw.point([cx + 1, head_top + 3], fill=(255, 255, 255))
        if is_female:
            draw.point([cx + 2, head_top + 2], fill=(40, 40, 40))
    elif direction == "left":
        draw.rectangle([cx - 3, head_top + 3, cx - 2, head_top + 4], fill=(40, 40, 40))
        draw.point([cx - 2, head_top + 3], fill=(255, 255, 255))
        if is_female:
            draw.point([cx - 3, head_top + 2], fill=(40, 40, 40))
    # up = back of head, no face


def generate_spritesheet(char: dict) -> Image.Image:
    """Generate a full 39-frame spritesheet for a character."""
    img = Image.new("RGBA", (FRAME * TOTAL_FRAMES, FRAME), (0, 0, 0, 0))

    def frame_pos(idx):
        return (idx * FRAME, 0)

    # Walk down: frames 0-2, 3-5, 6-8
    for cycle_start in (0, 3, 6):
        for i, phase in enumerate([0, 1, 2]):
            fx, fy = frame_pos(cycle_start + i)
            draw_character(img, fx, fy, char, "down", phase)

    # Walk up: frames 9-11
    for i, phase in enumerate([0, 1, 2]):
        fx, fy = frame_pos(9 + i)
        draw_character(img, fx, fy, char, "up", phase)

    # Walk right: frames 12-14, 15-17
    for cycle_start in (12, 15):
        for i, phase in enumerate([0, 1, 2]):
            fx, fy = frame_pos(cycle_start + i)
            draw_character(img, fx, fy, char, "right", phase)

    # Walk left: frames 18-20
    for i, phase in enumerate([0, 1, 2]):
        fx, fy = frame_pos(18 + i)
        draw_character(img, fx, fy, char, "left", phase)

    # Idle frames: 34=right, 35=down, 36=left, 37=up
    for idx, direction in [(34, "right"), (35, "down"), (36, "left"), (37, "up")]:
        fx, fy = frame_pos(idx)
        draw_character(img, fx, fy, char, direction, 0)

    return img


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for char in CHARACTERS:
        name = char["name"]
        img = generate_spritesheet(char)
        out_path = OUT_DIR / f"{name}Sprite.png"
        img.save(out_path)
        print(f"  Generated {out_path.name} ({img.size[0]}x{img.size[1]})")

    # Update SpriteConfig.ts with new sheets
    print(f"\nDone! {len(CHARACTERS)} spritesheets in {OUT_DIR}")
    print("\nAdd to SpriteConfig.ts SHEETS:")
    for char in CHARACTERS:
        name = char["name"]
        key = name.lower()
        print(f'  {key}: {{ path: "/sprites/{name}Sprite.png", frameSize: 32, frameCount: 39, anims: NOOB_ANIMS }},')


if __name__ == "__main__":
    main()
