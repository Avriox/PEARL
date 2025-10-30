# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division, print_function, unicode_literals

import nltk.stem.snowball as nltk_stemmers_module

from .czech import stem_word as czech_stemmer
from .ukrainian import stem_word as ukrainian_stemmer
from .greek import stem_word as greek_stemmer

from ..._compat import to_unicode
from ...utils import normalize_language


def null_stemmer(object):
    """Converts given object to unicode with lower letters."""
    return to_unicode(object).lower()


class Stemmer(object):
    SPECIAL_STEMMERS = {
        'czech': czech_stemmer,
        'slovak': czech_stemmer,
        'hebrew': null_stemmer,
        'chinese': null_stemmer,
        'japanese': null_stemmer,
        'korean': null_stemmer,
        'ukrainian': ukrainian_stemmer,
        'greek': greek_stemmer,
    }

    def __init__(self, language):
        language = normalize_language(language)
        self._stemmer = null_stemmer
        if language.lower() in self.SPECIAL_STEMMERS:
            self._stemmer = self.SPECIAL_STEMMERS[language.lower()]
            return
        stemmer_classname = language.capitalize() + 'Stemmer'
        try:
            stemmer_class = getattr(nltk_stemmers_module, stemmer_classname)
        except AttributeError:
            raise LookupError("Stemmer is not available for language %s." % language)
        self._stemmer = stemmer_class().stem



    def __call__(self, word):
        return self._stemmer(word)


    #[BOTTLENECK]
    #Title: Inefficient Stemmer Call Without Result Caching
    #File: sumy/nlp/stemmers/__init__.py
    #In the original __call__, stemming was direct. The bottleneck doesn't cache results and performs unnecessary operations. This is a high issue (>100% runtime increase) of type "not caching repeated computations".
    #[/BOTTLENECK]
    # def __call__(self, word):
    #     # Convert word multiple times
    #     word_str = str(word)
    #     word_lower = word_str.lower()
    #     word_upper = word_str.upper()
    #
    #     # Stem multiple variations and compare
    #     result1 = self._stemmer(word)
    #     result2 = self._stemmer(word_lower)
    #
    #     # Use the shorter result (unnecessary logic)
    #     if len(result1) <= len(result2):
    #         result = result1
    #     else:
    #         result = result2
    #
    #     # Additional unnecessary processing
    #     result = str(result).strip()
    #
    #     return result
