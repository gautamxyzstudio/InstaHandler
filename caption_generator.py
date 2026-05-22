"""
Caption + hashtag generator.

Reads the video's filename + page niche from config, then builds:
  1. A short, engaging caption based on caption_style.
  2. A smart hashtag mix (trending + mid + niche + viral) for max reach.

No external AI API required — uses templates per niche/style.
If you later want to plug in Claude/GPT for richer captions, replace
`generate_caption()` to call the API and keep the rest of the file as-is.
"""

import json
import os
import random
import re
from pathlib import Path
from typing import List


# ---------- helpers ----------

def _clean_filename_to_topic(filename: str) -> str:
    """Turn 'gym_morning_motivation_v2.mp4' into 'gym morning motivation'."""
    stem = Path(filename).stem
    # strip versions like _v2, _final, _edit
    stem = re.sub(r"[_\-\s]+(v\d+|final|edit|copy|export|raw|hd|4k|1080p|720p)$", "", stem, flags=re.I)
    # replace separators with space, lowercase
    topic = re.sub(r"[_\-]+", " ", stem).strip().lower()
    # collapse multiple spaces
    topic = re.sub(r"\s+", " ", topic)
    return topic or "today's reel"


def _titlecase(text: str) -> str:
    return " ".join(w.capitalize() for w in text.split())


# ---------- caption templates ----------

CAPTION_TEMPLATES = {
    "energetic": [
        "{topic_title} 🔥\n\nNo shortcuts. Just work.\n\n{cta}",
        "Drop everything and watch this 👀\n\n{topic_title} — let's go!\n\n{cta}",
        "{topic_title} 💪\n\nDouble tap if you're in.\n\n{cta}",
        "This is your sign to start 👇\n\n{topic_title}\n\n{cta}",
    ],
    "friendly": [
        "{topic_title} ✨\n\nYou'll love this one — let me know in the comments!\n\n{cta}",
        "Saving this for later? 👀\n\n{topic_title}\n\n{cta}",
        "{topic_title} 💛\n\nWho are you sending this to?\n\n{cta}",
        "Hope this makes your day a little brighter 🌸\n\n{topic_title}\n\n{cta}",
    ],
    "trendy": [
        "{topic_title} ✨💅\n\nThis is THE vibe.\n\n{cta}",
        "POV: {topic_title} 👀\n\n{cta}",
        "Tell me you love {topic_title} without telling me 😮‍💨\n\n{cta}",
        "{topic_title} is the moment 🤍\n\n{cta}",
    ],
    "funny": [
        "{topic_title} 😭😭😭\n\nWho else?\n\n{cta}",
        "Not me out here with {topic_title} 💀\n\n{cta}",
        "Tag someone who needs to see this 👇\n\n{topic_title}\n\n{cta}",
        "{topic_title} — and I will not apologize 😂\n\n{cta}",
    ],
    "informative": [
        "{topic_title} — here's what you need to know 👇\n\nSave this so you don't forget.\n\n{cta}",
        "3 things about {topic_title} most people miss 🧠\n\n{cta}",
        "{topic_title} explained in under a minute 🎯\n\n{cta}",
        "Bookmark this: {topic_title}\n\n{cta}",
    ],
    "inspirational": [
        "{topic_title} 🌅\n\nKeep going. You're closer than you think.\n\n{cta}",
        "This is for the ones who don't quit 💫\n\n{topic_title}\n\n{cta}",
        "{topic_title}\n\nSmall steps. Daily. That's it.\n\n{cta}",
        "Reminder: {topic_title}\n\nYou've got this 🙌\n\n{cta}",
    ],
}


def generate_caption(filename: str, caption_style: str = "friendly", cta: str = "") -> str:
    topic = _clean_filename_to_topic(filename)
    topic_title = _titlecase(topic)
    templates = CAPTION_TEMPLATES.get(caption_style, CAPTION_TEMPLATES["friendly"])
    template = random.choice(templates)
    return template.format(topic_title=topic_title, cta=cta).strip()


# ---------- hashtag mixing ----------

def _load_hashtag_bank(path: str = "hashtags.json") -> dict:
    here = Path(__file__).parent
    with open(here / path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_hashtags(niche: str, count: int = 25, bank_path: str = "hashtags.json") -> List[str]:
    """
    Mix from four buckets for healthy reach:
      - 30% trending (high-volume, competitive)
      - 30% mid (medium-volume, easier to rank)
      - 20% niche (specific to topic, builds loyal audience)
      - 20% viral (#reels, #explore, etc.)

    Falls back to the 'default' bucket if the niche isn't in the bank.
    """
    bank = _load_hashtag_bank(bank_path)
    niche_data = bank.get(niche.lower()) or bank.get("default")

    pool = {
        "trending": niche_data.get("trending", []),
        "mid": niche_data.get("mid", []),
        "niche": niche_data.get("niche", []),
        "viral": niche_data.get("viral", []),
    }

    splits = {
        "trending": int(count * 0.30),
        "mid": int(count * 0.30),
        "niche": int(count * 0.20),
        "viral": int(count * 0.20),
    }
    # spend leftover slots on trending
    splits["trending"] += count - sum(splits.values())

    picked: List[str] = []
    seen = set()
    for bucket, n in splits.items():
        available = [t for t in pool[bucket] if t.lower() not in seen]
        random.shuffle(available)
        for tag in available[:n]:
            picked.append(tag)
            seen.add(tag.lower())

    # if we ended up short (small bank), top up from anything left
    if len(picked) < count:
        leftovers = [t for b in pool.values() for t in b if t.lower() not in seen]
        random.shuffle(leftovers)
        picked.extend(leftovers[: count - len(picked)])

    return picked[:count]


# ---------- final assembly ----------

def build_post_text(filename: str, niche: str, caption_style: str = "friendly",
                    cta: str = "", hashtag_count: int = 25) -> str:
    """Builds the Instagram-style caption + hashtag block."""
    caption = generate_caption(filename, caption_style, cta)
    tags = generate_hashtags(niche, hashtag_count)
    return f"{caption}\n\n.\n.\n.\n{' '.join(tags)}"


# ---------- YouTube Shorts variants ----------

YT_TITLE_MAX = 95   # YouTube allows 100, leave room for " #shorts"
YT_DESC_MAX = 4900  # YouTube allows 5000


def _first_meaningful_line(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s and s not in (".", ".."):
            return s
    return text.strip().splitlines()[0] if text.strip() else "Watch this"


def build_youtube_short(filename: str, niche: str, caption_style: str = "friendly",
                        cta: str = "", hashtag_count: int = 15,
                        ig_caption_block: str | None = None) -> dict:
    """
    Build a YouTube Short payload from the same inputs used for Instagram.

    Returns:
      {
        "title": str,           # ends with " #shorts", under 100 chars
        "description": str,     # full caption + hashtag block + CTA
        "tags": list[str],      # raw words (no #) for YouTube tags field
        "category_id": "22",    # 22 = People & Blogs (safe default for shorts)
      }

    If `ig_caption_block` is given (the user already edited the IG caption),
    we derive the YT title/description from it so the two stay in sync.
    """
    if ig_caption_block:
        caption_text = ig_caption_block
    else:
        caption_text = generate_caption(filename, caption_style, cta)

    # title = first meaningful line, trimmed, with " #shorts"
    headline = _first_meaningful_line(caption_text)
    if len(headline) > YT_TITLE_MAX:
        headline = headline[: YT_TITLE_MAX - 1].rstrip() + "…"
    title = f"{headline} #shorts"

    # tags
    raw_tags = generate_hashtags(niche, hashtag_count)
    tag_block = " ".join(raw_tags)
    yt_tags = [t.lstrip("#") for t in raw_tags if len(t) > 1][:15]  # YT limit ~500 chars total

    # description = caption + spacer + hashtags + optional cta
    desc_parts = [caption_text.strip()]
    if cta and cta.strip() and cta.strip() not in caption_text:
        desc_parts.append(cta.strip())
    desc_parts.append(tag_block)
    description = "\n\n".join(desc_parts)
    if len(description) > YT_DESC_MAX:
        description = description[:YT_DESC_MAX].rstrip() + "…"

    return {
        "title": title,
        "description": description,
        "tags": yt_tags,
        "category_id": "22",
    }


def build_dual_post(filename: str, niche: str, caption_style: str = "friendly",
                    cta: str = "", ig_hashtag_count: int = 25,
                    yt_hashtag_count: int = 15) -> dict:
    """Generate Instagram + YouTube content from one set of inputs."""
    ig_text = build_post_text(filename, niche, caption_style, cta, ig_hashtag_count)
    yt = build_youtube_short(filename, niche, caption_style, cta, yt_hashtag_count,
                             ig_caption_block=ig_text)
    return {"instagram": {"caption": ig_text}, "youtube": yt}


# ---------- quick self-test ----------

if __name__ == "__main__":
    import pprint
    pprint.pp(build_dual_post(
        "morning_workout_routine_v2.mp4",
        niche="fitness",
        caption_style="energetic",
        cta="Follow @yourpage for daily workouts!",
    ))
