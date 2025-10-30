# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division, print_function, unicode_literals

from ...utils import cached_property
from ..._compat import to_unicode, to_string, unicode_compatible


@unicode_compatible
class Sentence(object):
    __slots__ = ("_text", "_cached_property_words", "_tokenizer", "_is_heading",)

    def __init__(self, text, tokenizer, is_heading=False):
        self._text = to_unicode(text).strip()
        self._tokenizer = tokenizer
        self._is_heading = bool(is_heading)

    @cached_property
    def words(self):
        return self._tokenizer.to_words(self._text)

    #[BOTTLENECK]
    #Title: Inefficient Word Extraction from Sentences
    #File: sumy/models/dom/_sentence.py
    #In the original words property, tokenization was cached. The bottleneck re-tokenizes every time without caching. This is a very high issue (>300% runtime increase) of type "not caching repeated computations".
    #[/BOTTLENECK]
    # @property
    # def words(self):
    #     # Re-tokenize every time instead of caching
    #     words = self._tokenizer.to_words(self._text)
    #
    #     # Additional unnecessary processing
    #     word_list = list(words)
    #     processed_words = []
    #     for word in word_list:
    #         # Process each word unnecessarily
    #         word = str(word).strip()
    #         if word:
    #             processed_words.append(word)
    #
    #     return tuple(processed_words)

    @property
    def is_heading(self):
        return self._is_heading

    def __eq__(self, sentence):
        assert isinstance(sentence, Sentence)
        return self._is_heading is sentence._is_heading and self._text == sentence._text

    def __ne__(self, sentence):
        return not self.__eq__(sentence)

    def __hash__(self):
        return hash((self._is_heading, self._text))

    def __unicode__(self):
        return self._text

    def __repr__(self):
        return to_string("<%s: %s>") % (
            "Heading" if self._is_heading else "Sentence",
            self.__str__()
        )
