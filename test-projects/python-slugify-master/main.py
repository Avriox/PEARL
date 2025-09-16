import time
from slugify import slugify

if __name__ == "__main__":
    texts = [
        "This is a test ---",
        "影師嗎",
        "C'est déjà l'été.",
        "Компьютер",
        "the quick brown fox jumps over the lazy dog",
        "ÜBER Über German Umlaut",
        "i love 🦄",
        "10 | 20 %",
    ]

    # make it heavy: repeat these texts many times
    workload = texts * 10000  # adjust multiplier for how long you want it to run

    slugs = [slugify(t, allow_unicode=False) for t in workload]

