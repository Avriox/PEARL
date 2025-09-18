import time
import textdistance

if __name__ == "__main__":
    s1 = "kitten" * 20
    s2 = "sitting" * 20

    algorithms = [
        textdistance.hamming,
        textdistance.levenshtein,
        textdistance.damerau_levenshtein,
        textdistance.jaro_winkler,
        textdistance.strcmp95,
        textdistance.jaccard,
        textdistance.sorensen,
        textdistance.tversky,
        textdistance.overlap,
        textdistance.cosine,
        textdistance.monge_elkan,
        textdistance.bag,
        textdistance.lcsseq,
        textdistance.lcsstr,
        textdistance.ratcliff_obershelp,
        textdistance.mra,
        textdistance.editex,
        textdistance.prefix,
        textdistance.postfix,
        textdistance.length,
        textdistance.identity,
        textdistance.matrix,
    ]

    # Add compression-based algorithms if available
    for name in ("bz2_ncd", "lzma_ncd", "zlib_ncd"):
        if hasattr(textdistance, name):
            algorithms.append(getattr(textdistance, name))

    for algo in algorithms:
        try:
            # Each algorithm instance is callable
            _ = algo(s1, s2)
        except Exception:
            pass
