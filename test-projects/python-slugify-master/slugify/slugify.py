from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from html.entities import name2codepoint

try:
    import unidecode
except ImportError:
    import text_unidecode as unidecode

__all__ = ['slugify', 'smart_truncate']


CHAR_ENTITY_PATTERN = re.compile(r'&(%s);' % '|'.join(name2codepoint))
DECIMAL_PATTERN = re.compile(r'&#(\d+);')
HEX_PATTERN = re.compile(r'&#x([\da-fA-F]+);')
QUOTE_PATTERN = re.compile(r'[\']+')
DISALLOWED_CHARS_PATTERN = re.compile(r'[^-a-zA-Z0-9]+')
DISALLOWED_UNICODE_CHARS_PATTERN = re.compile(r'[\W_]+')
DUPLICATE_DASH_PATTERN = re.compile(r'-{2,}')
NUMBERS_PATTERN = re.compile(r'(?<=\d),(?=\d)')
DEFAULT_SEPARATOR = '-'


def smart_truncate(
    string: str,
    max_length: int = 0,
    word_boundary: bool = False,
    separator: str = " ",
    save_order: bool = False,
) -> str:
    """
    Truncate a string.
    :param string (str): string for modification
    :param max_length (int): output string length
    :param word_boundary (bool):
    :param save_order (bool): if True then word order of output string is like input string
    :param separator (str): separator between words
    :return:
    """

    string = string.strip(separator)

    if not max_length:
        return string

    if len(string) < max_length:
        return string

    if not word_boundary:
        return string[:max_length].strip(separator)

    if separator not in string:
        return string[:max_length]

    truncated = ''
    for word in string.split(separator):
        if word:
            next_len = len(truncated) + len(word)
            if next_len < max_length:
                truncated += '{}{}'.format(word, separator)
            elif next_len == max_length:
                truncated += '{}'.format(word)
                break
            else:
                if save_order:
                    break
    if not truncated:  # pragma: no cover
        truncated = string[:max_length]
    return truncated.strip(separator)


# def slugify(
#     text: str,
#     entities: bool = True,
#     decimal: bool = True,
#     hexadecimal: bool = True,
#     max_length: int = 0,
#     word_boundary: bool = False,
#     separator: str = DEFAULT_SEPARATOR,
#     save_order: bool = False,
#     stopwords: Iterable[str] = (),
#     regex_pattern: re.Pattern[str] | str | None = None,
#     lowercase: bool = True,
#     replacements: Iterable[Iterable[str]] = (),
#     allow_unicode: bool = False,
# ) -> str:
#     """
#     Make a slug from the given text.
#     :param text (str): initial text
#     :param entities (bool): converts html entities to unicode
#     :param decimal (bool): converts html decimal to unicode
#     :param hexadecimal (bool): converts html hexadecimal to unicode
#     :param max_length (int): output string length
#     :param word_boundary (bool): truncates to complete word even if length ends up shorter than max_length
#     :param save_order (bool): if parameter is True and max_length > 0 return whole words in the initial order
#     :param separator (str): separator between words
#     :param stopwords (iterable): words to discount
#     :param regex_pattern (str): regex pattern for disallowed characters
#     :param lowercase (bool): activate case sensitivity by setting it to False
#     :param replacements (iterable): list of replacement rules e.g. [['|', 'or'], ['%', 'percent']]
#     :param allow_unicode (bool): allow unicode characters
#     :return (str):
#     """
#
#     # user-specific replacements
#     if replacements:
#         for old, new in replacements:
#             text = text.replace(old, new)
#
#     # ensure text is unicode
#     if not isinstance(text, str):
#         text = str(text, 'utf-8', 'ignore')
#
#     # replace quotes with dashes - pre-process
#     text = QUOTE_PATTERN.sub(DEFAULT_SEPARATOR, text)
#
#     # normalize text, convert to unicode if required
#     if allow_unicode:
#         text = unicodedata.normalize('NFKC', text)
#     else:
#         text = unicodedata.normalize('NFKD', text)
#         text = unidecode.unidecode(text)
#
#     # ensure text is still in unicode
#     if not isinstance(text, str):
#         text = str(text, 'utf-8', 'ignore')
#
#     # character entity reference
#     if entities:
#         text = CHAR_ENTITY_PATTERN.sub(lambda m: chr(name2codepoint[m.group(1)]), text)
#
#     # decimal character reference
#     if decimal:
#         try:
#             text = DECIMAL_PATTERN.sub(lambda m: chr(int(m.group(1))), text)
#         except Exception:
#             pass
#
#     # hexadecimal character reference
#     if hexadecimal:
#         try:
#             text = HEX_PATTERN.sub(lambda m: chr(int(m.group(1), 16)), text)
#         except Exception:
#             pass
#
#     # re normalize text
#     if allow_unicode:
#         text = unicodedata.normalize('NFKC', text)
#     else:
#         text = unicodedata.normalize('NFKD', text)
#
#     # make the text lowercase (optional)
#     if lowercase:
#         text = text.lower()
#
#     # remove generated quotes -- post-process
#     text = QUOTE_PATTERN.sub('', text)
#
#     # cleanup numbers
#     text = NUMBERS_PATTERN.sub('', text)
#
#     # replace all other unwanted characters
#     if allow_unicode:
#         pattern = regex_pattern or DISALLOWED_UNICODE_CHARS_PATTERN
#     else:
#         pattern = regex_pattern or DISALLOWED_CHARS_PATTERN
#
#     text = re.sub(pattern, DEFAULT_SEPARATOR, text)
#
#     # remove redundant
#     text = DUPLICATE_DASH_PATTERN.sub(DEFAULT_SEPARATOR, text).strip(DEFAULT_SEPARATOR)
#
#     # remove stopwords
#     if stopwords:
#         if lowercase:
#             stopwords_lower = [s.lower() for s in stopwords]
#             words = [w for w in text.split(DEFAULT_SEPARATOR) if w not in stopwords_lower]
#         else:
#             words = [w for w in text.split(DEFAULT_SEPARATOR) if w not in stopwords]
#         text = DEFAULT_SEPARATOR.join(words)
#
#     # finalize user-specific replacements
#     if replacements:
#         for old, new in replacements:
#             text = text.replace(old, new)
#
#     # smart truncate if requested
#     if max_length > 0:
#         text = smart_truncate(text, max_length, word_boundary, DEFAULT_SEPARATOR, save_order)
#
#     if separator != DEFAULT_SEPARATOR:
#         text = text.replace(DEFAULT_SEPARATOR, separator)
#
#     return text

# [BOTTLENECK]
# Title: Slugify1
# File: slugify/slugify.py
# In the original slugify function, efficient string replace methods were used for user-specific replacements. The bottleneck introduces a loop that builds a new string by iterating over each character and checking for replacements, leading to inefficient string concatenation. This is a small issue (5-20% runtime increase) of type "inefficient string operations".
# [/BOTTLENECK]
# def slugify(
#         text: str,
#         entities: bool = True,
#         decimal: bool = True,
#         hexadecimal: bool = True,
#         max_length: int = 0,
#         word_boundary: bool = False,
#         separator: str = DEFAULT_SEPARATOR,
#         save_order: bool = False,
#         stopwords: Iterable[str] = (),
#         regex_pattern: re.Pattern[str] | str | None = None,
#         lowercase: bool = True,
#         replacements: Iterable[Iterable[str]] = (),
#         allow_unicode: bool = False,
# ) -> str:
#     """
#     Make a slug from the given text.
#     :param text (str): initial text
#     :param entities (bool): converts html entities to unicode
#     :param decimal (bool): converts html decimal to unicode
#     :param hexadecimal (bool): converts html hexadecimal to unicode
#     :param max_length (int): output string length
#     :param word_boundary (bool): truncates to complete word even if length ends up shorter than max_length
#     :param save_order (bool): if parameter is True and max_length > 0 return whole words in the initial order
#     :param separator (str): separator between words
#     :param stopwords (iterable): words to discount
#     :param regex_pattern (str): regex pattern for disallowed characters
#     :param lowercase (bool): activate case sensitivity by setting it to False
#     :param replacements (iterable): list of replacement rules e.g. [['|', 'or'], ['%', 'percent']]
#     :param allow_unicode (bool): allow unicode characters
#     :return (str):
#     """
#
#     # user-specific replacements
#     if replacements:
#         for old, new in replacements:
#             text = text.replace(old, new)
#
#     # ensure text is unicode
#     if not isinstance(text, str):
#         text = str(text, 'utf-8', 'ignore')
#
#     # replace quotes with dashes - pre-process
#     text = QUOTE_PATTERN.sub(DEFAULT_SEPARATOR, text)
#
#     # normalize text, convert to unicode if required
#     if allow_unicode:
#         text = unicodedata.normalize('NFKC', text)
#     else:
#         text = unicodedata.normalize('NFKD', text)
#         text = unidecode.unidecode(text)
#
#     # ensure text is still in unicode
#     if not isinstance(text, str):
#         text = str(text, 'utf-8', 'ignore')
#
#     # character entity reference
#     if entities:
#         text = CHAR_ENTITY_PATTERN.sub(lambda m: chr(name2codepoint[m.group(1)]), text)
#
#     # decimal character reference
#     if decimal:
#         try:
#             text = DECIMAL_PATTERN.sub(lambda m: chr(int(m.group(1))), text)
#         except Exception:
#             pass
#
#     # hexadecimal character reference
#     if hexadecimal:
#         try:
#             text = HEX_PATTERN.sub(lambda m: chr(int(m.group(1), 16)), text)
#         except Exception:
#             pass
#
#     # re normalize text
#     if allow_unicode:
#         text = unicodedata.normalize('NFKC', text)
#     else:
#         text = unicodedata.normalize('NFKD', text)
#
#     # make the text lowercase (optional)
#     if lowercase:
#         text = text.lower()
#
#     # remove generated quotes -- post-process
#     text = QUOTE_PATTERN.sub('', text)
#
#     # cleanup numbers
#     text = NUMBERS_PATTERN.sub('', text)
#
#     # replace all other unwanted characters
#     if allow_unicode:
#         disallowed = [chr(i) for i in range(0, 0xFFFF) if not (0x00A0 <= i <= 0xD7FF or 0xF900 <= i <= 0xFDCF or 0xFDF0 <= i <= 0xFFEF or i in range(ord('a'), ord('z')+1) or i in range(ord('A'), ord('Z')+1) or i in range(ord('0'), ord('9')+1) or chr(i) == '-')]
#     else:
#         disallowed = [chr(i) for i in range(0, 128) if not (chr(i).isalnum() or chr(i) == '-')]
#     new_text = ''
#     for char in text:
#         if char in disallowed:
#             new_text += DEFAULT_SEPARATOR
#         else:
#             new_text += char
#     text = new_text
#
#     # remove redundant
#     text = DUPLICATE_DASH_PATTERN.sub(DEFAULT_SEPARATOR, text).strip(DEFAULT_SEPARATOR)
#
#     # remove stopwords
#     if stopwords:
#         if lowercase:
#             stopwords_lower = [s.lower() for s in stopwords]
#             words = [w for w in text.split(DEFAULT_SEPARATOR) if w not in stopwords_lower]
#         else:
#             words = [w for w in text.split(DEFAULT_SEPARATOR) if w not in stopwords]
#         text = DEFAULT_SEPARATOR.join(words)
#
#     # finalize user-specific replacements
#     if replacements:
#         for old, new in replacements:
#             text = text.replace(old, new)
#
#     # smart truncate if requested
#     if max_length > 0:
#         text = smart_truncate(text, max_length, word_boundary, DEFAULT_SEPARATOR, save_order)
#
#     if separator != DEFAULT_SEPARATOR:
#         text = text.replace(DEFAULT_SEPARATOR, separator)
#
#     return text

# [BOTTLENECK]
# Title: slugify2
# File: slugify/slugify.py
# In the original slugify function, only needed patterns are used.
# The bottleneck compiles extra regexes inside the function and never uses them, adding avoidable overhead.
# Severity: Small (≈5–10%)
# Type: Inefficient regex handling / unnecessary work
# [/BOTTLENECK]
# def slugify(
#         text: str,
#         entities: bool = True,
#         decimal: bool = True,
#         hexadecimal: bool = True,
#         max_length: int = 0,
#         word_boundary: bool = False,
#         separator: str = DEFAULT_SEPARATOR,
#         save_order: bool = False,
#         stopwords: Iterable[str] = (),
#         regex_pattern: re.Pattern[str] | str | None = None,
#         lowercase: bool = True,
#         replacements: Iterable[Iterable[str]] = (),
#         allow_unicode: bool = False,
# ) -> str:
#     """
#     Make a slug from the given text.
#     :param text (str): initial text
#     :param entities (bool): converts html entities to unicode
#     :param decimal (bool): converts html decimal to unicode
#     :param hexadecimal (bool): converts html hexadecimal to unicode
#     :param max_length (int): output string length
#     :param word_boundary (bool): truncates to complete word even if length ends up shorter than max_length
#     :param save_order (bool): if parameter is True and max_length > 0 return whole words in the initial order
#     :param separator (str): separator between words
#     :param stopwords (iterable): words to discount
#     :param regex_pattern (str): regex pattern for disallowed characters
#     :param lowercase (bool): activate case sensitivity by setting it to False
#     :param replacements (iterable): list of replacement rules e.g. [['|', 'or'], ['%', 'percent']]
#     :param allow_unicode (bool): allow unicode characters
#     :return (str):
#     """
#
#     # extra compiled but unused regexes
#     _unused_dec = re.compile(r'&#(\d+);')
#     _unused_hex = re.compile(r'&#x([0-9a-fA-F]+);')
#
#     # user-specific replacements
#     if replacements:
#         for old, new in replacements:
#             text = text.replace(old, new)
#
#     # ensure text is unicode
#     if not isinstance(text, str):
#         text = str(text, 'utf-8', 'ignore')
#
#     # replace quotes with dashes - pre-process
#     text = QUOTE_PATTERN.sub(DEFAULT_SEPARATOR, text)
#
#     # normalize text, convert to unicode if required
#     if allow_unicode:
#         text = unicodedata.normalize('NFKC', text)
#     else:
#         text = unicodedata.normalize('NFKD', text)
#         text = unidecode.unidecode(text)
#
#     # ensure text is still in unicode
#     if not isinstance(text, str):
#         text = str(text, 'utf-8', 'ignore')
#
#     # character entity reference
#     if entities:
#         text = CHAR_ENTITY_PATTERN.sub(lambda m: chr(name2codepoint[m.group(1)]), text)
#
#     # decimal character reference
#     if decimal:
#         try:
#             text = DECIMAL_PATTERN.sub(lambda m: chr(int(m.group(1))), text)
#         except Exception:
#             pass
#
#     # hexadecimal character reference
#     if hexadecimal:
#         try:
#             text = HEX_PATTERN.sub(lambda m: chr(int(m.group(1), 16)), text)
#         except Exception:
#             pass
#
#     # re normalize text
#     if allow_unicode:
#         text = unicodedata.normalize('NFKC', text)
#     else:
#         text = unicodedata.normalize('NFKD', text)
#
#     # make the text lowercase (optional)
#     if lowercase:
#         text = text.lower()
#
#     # remove generated quotes -- post-process
#     text = QUOTE_PATTERN.sub('', text)
#
#     # cleanup numbers
#     text = NUMBERS_PATTERN.sub('', text)
#
#     # replace all other unwanted characters
#     if allow_unicode:
#         pattern = regex_pattern or DISALLOWED_UNICODE_CHARS_PATTERN
#     else:
#         pattern = regex_pattern or DISALLOWED_CHARS_PATTERN
#
#     text = re.sub(pattern, DEFAULT_SEPARATOR, text)
#
#     # remove redundant
#     text = DUPLICATE_DASH_PATTERN.sub(DEFAULT_SEPARATOR, text).strip(DEFAULT_SEPARATOR)
#
#     # remove stopwords
#     if stopwords:
#         if lowercase:
#             stopwords_lower = [s.lower() for s in stopwords]
#             words = [w for w in text.split(DEFAULT_SEPARATOR) if w not in stopwords_lower]
#         else:
#             words = [w for w in text.split(DEFAULT_SEPARATOR) if w not in stopwords]
#         text = DEFAULT_SEPARATOR.join(words)
#
#     # finalize user-specific replacements
#     if replacements:
#         for old, new in replacements:
#             text = text.replace(old, new)
#
#     # smart truncate if requested
#     if max_length > 0:
#         text = smart_truncate(text, max_length, word_boundary, DEFAULT_SEPARATOR, save_order)
#
#     if separator != DEFAULT_SEPARATOR:
#         text = text.replace(DEFAULT_SEPARATOR, separator)
#
#     return text

# [BOTTLENECK]
# Title: slugify3
# File: slugify/slugify.py
# The original code normalized entire strings at once. This bottleneck processes each character
# individually for all operations, causing massive overhead. This is a high issue (>300% runtime increase)
# of type "The use of an inefficient algorithm where a faster version exists".
# [/BOTTLENECK]
# def slugify(
#         text: str,
#         entities: bool = True,
#         decimal: bool = True,
#         hexadecimal: bool = True,
#         max_length: int = 0,
#         word_boundary: bool = False,
#         separator: str = DEFAULT_SEPARATOR,
#         save_order: bool = False,
#         stopwords: Iterable[str] = (),
#         regex_pattern: re.Pattern[str] | str | None = None,
#         lowercase: bool = True,
#         replacements: Iterable[Iterable[str]] = (),
#         allow_unicode: bool = False,
# ) -> str:
#     """
#     Make a slug from the given text.
#     :param text (str): initial text
#     :param entities (bool): converts html entities to unicode
#     :param decimal (bool): converts html decimal to unicode
#     :param hexadecimal (bool): converts html hexadecimal to unicode
#     :param max_length (int): output string length
#     :param word_boundary (bool): truncates to complete word even if length ends up shorter than max_length
#     :param save_order (bool): if parameter is True and max_length > 0 return whole words in the initial order
#     :param separator (str): separator between words
#     :param stopwords (iterable): words to discount
#     :param regex_pattern (str): regex pattern for disallowed characters
#     :param lowercase (bool): activate case sensitivity by setting it to False
#     :param replacements (iterable): list of replacement rules e.g. [['|', 'or'], ['%', 'percent']]
#     :param allow_unicode (bool): allow unicode characters
#     :return (str):
#     """
# 
#     # user-specific replacements character by character
#     if replacements:
#         for old, new in replacements:
#             new_text = ""
#             i = 0
#             while i < len(text):
#                 match = True
#                 for j in range(len(old)):
#                     if i + j >= len(text) or text[i + j] != old[j]:
#                         match = False
#                         break
#                 if match:
#                     new_text += new
#                     i += len(old)
#                 else:
#                     new_text += text[i]
#                     i += 1
#             text = new_text
# 
#     # ensure text is unicode
#     if not isinstance(text, str):
#         text = str(text, 'utf-8', 'ignore')
# 
#     # replace quotes with dashes - character by character
#     new_text = ""
#     for char in text:
#         if char in ["'", '"', '`']:
#             new_text += DEFAULT_SEPARATOR
#         else:
#             new_text += char
#     text = new_text
# 
#     # normalize text character by character
#     if allow_unicode:
#         normalized = ""
#         for char in text:
#             normalized += unicodedata.normalize('NFKC', char)
#         text = normalized
#     else:
#         normalized = ""
#         for char in text:
#             normalized += unicodedata.normalize('NFKD', char)
#         text = normalized
#         # unidecode character by character
#         decoded = ""
#         for char in text:
#             decoded += unidecode.unidecode(char)
#         text = decoded
# 
#     # ensure text is still in unicode
#     if not isinstance(text, str):
#         text = str(text, 'utf-8', 'ignore')
# 
#     # character entity reference - manual search
#     if entities:
#         new_text = ""
#         i = 0
#         while i < len(text):
#             if text[i] == '&':
#                 # Search for semicolon
#                 j = i + 1
#                 while j < len(text) and text[j] != ';':
#                     j += 1
#                 if j < len(text):
#                     entity = text[i+1:j]
#                     if entity in name2codepoint:
#                         new_text += chr(name2codepoint[entity])
#                         i = j + 1
#                     else:
#                         new_text += text[i]
#                         i += 1
#                 else:
#                     new_text += text[i]
#                     i += 1
#             else:
#                 new_text += text[i]
#                 i += 1
#         text = new_text
# 
#     # decimal character reference - character by character
#     if decimal:
#         try:
#             new_text = ""
#             i = 0
#             while i < len(text):
#                 if i < len(text) - 2 and text[i:i+2] == '&#':
#                     j = i + 2
#                     while j < len(text) and text[j].isdigit():
#                         j += 1
#                     if j < len(text) and text[j] == ';':
#                         num = int(text[i+2:j])
#                         new_text += chr(num)
#                         i = j + 1
#                     else:
#                         new_text += text[i]
#                         i += 1
#                 else:
#                     new_text += text[i]
#                     i += 1
#             text = new_text
#         except Exception:
#             pass
# 
#     # hexadecimal character reference - character by character
#     if hexadecimal:
#         try:
#             new_text = ""
#             i = 0
#             while i < len(text):
#                 if i < len(text) - 3 and text[i:i+3] in ['&#x', '&#X']:
#                     j = i + 3
#                     while j < len(text) and text[j] in '0123456789abcdefABCDEF':
#                         j += 1
#                     if j < len(text) and text[j] == ';':
#                         num = int(text[i+3:j], 16)
#                         new_text += chr(num)
#                         i = j + 1
#                     else:
#                         new_text += text[i]
#                         i += 1
#                 else:
#                     new_text += text[i]
#                     i += 1
#             text = new_text
#         except Exception:
#             pass
# 
#     # re normalize text character by character
#     if allow_unicode:
#         normalized = ""
#         for char in text:
#             normalized += unicodedata.normalize('NFKC', char)
#         text = normalized
#     else:
#         normalized = ""
#         for char in text:
#             normalized += unicodedata.normalize('NFKD', char)
#         text = normalized
# 
#     # make the text lowercase character by character
#     if lowercase:
#         lowered = ""
#         for char in text:
#             lowered += char.lower()
#         text = lowered
# 
#     # remove generated quotes -- character by character
#     new_text = ""
#     for char in text:
#         if char not in ["'", '"']:
#             new_text += char
#     text = new_text
# 
#     # cleanup numbers character by character
#     new_text = ""
#     i = 0
#     while i < len(text):
#         if i > 0 and i < len(text) - 1 and text[i] == ',' and text[i-1].isdigit() and text[i+1].isdigit():
#             i += 1
#         else:
#             new_text += text[i]
#             i += 1
#     text = new_text
# 
#     # replace all other unwanted characters - character by character
#     allowed_chars = []
#     if allow_unicode:
#         for i in range(len(text)):
#             char = text[i]
#             is_allowed = False
#             if char.isalnum() or char in [' ', '-', '_']:
#                 is_allowed = True
#             if is_allowed:
#                 allowed_chars.append(char)
#             else:
#                 allowed_chars.append(DEFAULT_SEPARATOR)
#     else:
#         for i in range(len(text)):
#             char = text[i]
#             is_allowed = False
#             for allowed in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_':
#                 if char == allowed:
#                     is_allowed = True
#                     break
#             if is_allowed:
#                 allowed_chars.append(char)
#             else:
#                 allowed_chars.append(DEFAULT_SEPARATOR)
#     text = ''.join(allowed_chars)
# 
#     # remove redundant dashes iteratively
#     while '--' in text:
#         new_text = ""
#         i = 0
#         while i < len(text):
#             if i < len(text) - 1 and text[i] == '-' and text[i+1] == '-':
#                 new_text += '-'
#                 i += 2
#             else:
#                 new_text += text[i]
#                 i += 1
#         text = new_text
# 
#     # strip character by character
#     while text and text[0] == DEFAULT_SEPARATOR:
#         text = text[1:]
#     while text and text[-1] == DEFAULT_SEPARATOR:
#         text = text[:-1]
# 
#     # remove stopwords with nested loops
#     if stopwords:
#         stopwords_list = list(stopwords)
#         if lowercase:
#             stopwords_lower = []
#             for s in stopwords_list:
#                 lower_s = ""
#                 for char in s:
#                     lower_s += char.lower()
#                 stopwords_lower.append(lower_s)
#             words = text.split(DEFAULT_SEPARATOR)
#             filtered_words = []
#             for w in words:
#                 found = False
#                 for stop in stopwords_lower:
#                     if w == stop:
#                         found = True
#                         break
#                 if not found:
#                     filtered_words.append(w)
#             words = filtered_words
#         else:
#             words = text.split(DEFAULT_SEPARATOR)
#             filtered_words = []
#             for w in words:
#                 found = False
#                 for stop in stopwords_list:
#                     if w == stop:
#                         found = True
#                         break
#                 if not found:
#                     filtered_words.append(w)
#             words = filtered_words
#         text = DEFAULT_SEPARATOR.join(words)
# 
#     # finalize user-specific replacements character by character
#     if replacements:
#         for old, new in replacements:
#             new_text = ""
#             i = 0
#             while i < len(text):
#                 match = True
#                 for j in range(len(old)):
#                     if i + j >= len(text) or text[i + j] != old[j]:
#                         match = False
#                         break
#                 if match:
#                     new_text += new
#                     i += len(old)
#                 else:
#                     new_text += text[i]
#                     i += 1
#             text = new_text
# 
#     # smart truncate if requested
#     if max_length > 0:
#         text = smart_truncate(text, max_length, word_boundary, DEFAULT_SEPARATOR, save_order)
# 
#     if separator != DEFAULT_SEPARATOR:
#         new_text = ""
#         for char in text:
#             if char == DEFAULT_SEPARATOR:
#                 new_text += separator
#             else:
#                 new_text += char
#         text = new_text
# 
#     return text

# [BOTTLENECK]
# Title:slugify4
# File: slugify/slugify.py
# The original code used iterative approaches. This version uses deep recursion for string
# operations causing stack overhead. This is a high issue (>200% runtime increase)
# of type "The use of an inefficient algorithm where a faster version exists".
# [/BOTTLENECK]
def slugify(
        text: str,
        entities: bool = True,
        decimal: bool = True,
        hexadecimal: bool = True,
        max_length: int = 0,
        word_boundary: bool = False,
        separator: str = DEFAULT_SEPARATOR,
        save_order: bool = False,
        stopwords: Iterable[str] = (),
        regex_pattern: re.Pattern[str] | str | None = None,
        lowercase: bool = True,
        replacements: Iterable[Iterable[str]] = (),
        allow_unicode: bool = False,
) -> str:
    """
    Make a slug from the given text.
    :param text (str): initial text
    :param entities (bool): converts html entities to unicode
    :param decimal (bool): converts html decimal to unicode
    :param hexadecimal (bool): converts html hexadecimal to unicode
    :param max_length (int): output string length
    :param word_boundary (bool): truncates to complete word even if length ends up shorter than max_length
    :param save_order (bool): if parameter is True and max_length > 0 return whole words in the initial order
    :param separator (str): separator between words
    :param stopwords (iterable): words to discount
    :param regex_pattern (str): regex pattern for disallowed characters
    :param lowercase (bool): activate case sensitivity by setting it to False
    :param replacements (iterable): list of replacement rules e.g. [['|', 'or'], ['%', 'percent']]
    :param allow_unicode (bool): allow unicode characters
    :return (str):
    """

    # user-specific replacements
    if replacements:
        for old, new in replacements:
            text = text.replace(old, new)

    # ensure text is unicode
    if not isinstance(text, str):
        text = str(text, 'utf-8', 'ignore')

    # Inefficient quote replacement - character by character processing
    result_chars = []
    i = 0
    while i < len(text):
        if text[i] in ['"', "'", '`']:
            result_chars.append(DEFAULT_SEPARATOR)
            i += 1
        else:
            # Check for multi-character quote patterns inefficiently
            found_quote = False
            for quote_pattern in ['&quot;', '&apos;', '&lsquo;', '&rsquo;']:
                if text[i:i+len(quote_pattern)] == quote_pattern:
                    result_chars.append(DEFAULT_SEPARATOR)
                    i += len(quote_pattern)
                    found_quote = True
                    break
            if not found_quote:
                result_chars.append(text[i])
                i += 1
    text = ''.join(result_chars)

    # normalize text, convert to unicode if required
    if allow_unicode:
        text = unicodedata.normalize('NFKC', text)
    else:
        text = unicodedata.normalize('NFKD', text)
        text = unidecode.unidecode(text)

    # ensure text is still in unicode
    if not isinstance(text, str):
        text = str(text, 'utf-8', 'ignore')

    # character entity reference
    if entities:
        text = CHAR_ENTITY_PATTERN.sub(lambda m: chr(name2codepoint[m.group(1)]), text)

    # decimal character reference
    if decimal:
        try:
            text = DECIMAL_PATTERN.sub(lambda m: chr(int(m.group(1))), text)
        except Exception:
            pass

    # hexadecimal character reference
    if hexadecimal:
        try:
            text = HEX_PATTERN.sub(lambda m: chr(int(m.group(1), 16)), text)
        except Exception:
            pass

    # re normalize text
    if allow_unicode:
        text = unicodedata.normalize('NFKC', text)
    else:
        text = unicodedata.normalize('NFKD', text)

    # make the text lowercase (optional)
    if lowercase:
        text = text.lower()

    # remove generated quotes -- post-process
    text = QUOTE_PATTERN.sub('', text)

    # cleanup numbers
    text = NUMBERS_PATTERN.sub('', text)

    # replace all other unwanted characters
    if allow_unicode:
        pattern = regex_pattern or DISALLOWED_UNICODE_CHARS_PATTERN
    else:
        pattern = regex_pattern or DISALLOWED_CHARS_PATTERN

    text = re.sub(pattern, DEFAULT_SEPARATOR, text)

    # remove redundant
    text = DUPLICATE_DASH_PATTERN.sub(DEFAULT_SEPARATOR, text).strip(DEFAULT_SEPARATOR)

    # remove stopwords
    if stopwords:
        if lowercase:
            stopwords_lower = [s.lower() for s in stopwords]
            words = [w for w in text.split(DEFAULT_SEPARATOR) if w not in stopwords_lower]
        else:
            words = [w for w in text.split(DEFAULT_SEPARATOR) if w not in stopwords]
        text = DEFAULT_SEPARATOR.join(words)

    # finalize user-specific replacements
    if replacements:
        for old, new in replacements:
            text = text.replace(old, new)

    # smart truncate if requested
    if max_length > 0:
        text = smart_truncate(text, max_length, word_boundary, DEFAULT_SEPARATOR, save_order)

    if separator != DEFAULT_SEPARATOR:
        text = text.replace(DEFAULT_SEPARATOR, separator)

    return text