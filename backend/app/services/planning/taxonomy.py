import re

CATEGORY_ALIASES = {
    "tech": "technology",
    "technology": "technology",
    "ai": "technology",
    "artificial_intelligence": "technology",
    "machine_learning": "technology",
    "startup": "technology",
    "workshop": "workshops",
    "workshops": "workshops",
    "music": "live_music",
    "live_music": "live_music",
    "concert": "live_music",
    "concerts": "live_music",
    "jazz": "live_music",
    "food": "food",
    "dining": "food",
    "comedy": "comedy",
    "art": "arts",
    "arts": "arts",
    "exhibition": "arts",
    "film": "film",
    "movie": "film",
    "movies": "film",
    "outdoors": "outdoors",
    "photography": "outdoors",
    "nightlife": "nightlife",
}

CUISINE_ALIASES = {
    "japanese": "japanese",
    "sushi": "japanese",
    "ramen": "japanese",
    "izakaya": "japanese",
    "italian": "italian",
    "pizza": "italian",
    "thai": "thai",
    "indian": "indian",
    "korean": "korean",
    "mexican": "mexican",
    "canadian": "canadian",
    "cafe": "cafe",
    "coffee": "cafe",
    "cocktail": "cocktail_bar",
    "cocktails": "cocktail_bar",
    "cocktail_bar": "cocktail_bar",
}

LABELS = {
    "technology": "technology",
    "workshops": "workshops",
    "live_music": "live music",
    "food": "food",
    "comedy": "comedy",
    "arts": "art",
    "film": "film",
    "outdoors": "the outdoors",
    "nightlife": "nightlife",
    "japanese": "Japanese food",
    "italian": "Italian food",
    "thai": "Thai food",
    "indian": "Indian food",
    "korean": "Korean food",
    "mexican": "Mexican food",
    "canadian": "Canadian food",
    "cafe": "cafes",
    "cocktail_bar": "cocktail bars",
}


def slugify(value: str) -> str:
    text = value.strip().lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


def normalize_token(value: str, *, cuisine: bool = False) -> str:
    slug = slugify(value)
    if cuisine:
        return CUISINE_ALIASES.get(slug, slug)
    if slug in CUISINE_ALIASES and slug not in CATEGORY_ALIASES:
        return CUISINE_ALIASES[slug]
    return CATEGORY_ALIASES.get(slug, slug)


def normalize_list(values: list[str], *, cuisine: bool = False, limit: int = 12) -> list[str]:
    seen: list[str] = []
    for value in values:
        token = normalize_token(value, cuisine=cuisine)
        if token and token not in seen:
            seen.append(token)
        if len(seen) >= limit:
            break
    return seen


def humanize(tokens: list[str]) -> str:
    labels = [LABELS.get(token, token.replace("_", " ")) for token in tokens if token]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"
