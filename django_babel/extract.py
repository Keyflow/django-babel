# -*- coding: utf-8 -*-
try:
    from django.template import Lexer, TOKEN_TEXT, TOKEN_VAR, TOKEN_BLOCK
except ImportError:
    # Django 1.8 moved most stuff to .base
    from django.template.base import Lexer, TOKEN_TEXT, TOKEN_VAR, TOKEN_BLOCK, TOKEN_COMMENT

try:
    from django.utils.translation import trim_whitespace as trim_django
except ImportError:
    trim_django = False

from django.utils.encoding import smart_text
from django.utils.translation.trans_real import (
    inline_re, block_re, endblock_re, plural_re, constant_re)


def trim_whitespace(string):
    """Trim whitespace.

    This is only supported in Django>=1.7. This method help in cases of older
    Django versions.
    """
    if trim_django:
        return trim_django(string)
    return string


def join_tokens(tokens, trim=False):
    message = ''.join(tokens)
    if trim:
        message = trim_whitespace(message)
    return message


def strip_quotes(s):
    if (s[0] == s[-1]) and s.startswith(("'", '"')):
        return s[1:-1]
    return s


def extract_django(fileobj, keywords, comment_tags, options):
    """Extract messages from Django template files.

    :param fileobj: the file-like object the messages should be extracted from
    :param keywords: a list of keywords (i.e. function names) that should
                     be recognized as translation functions
    :param comment_tags: a list of translator tags to search for and
                         include in the results
    :param options: a dictionary of additional options (optional)
    :return: an iterator over ``(lineno, funcname, message, comments)``
             tuples
    :rtype: ``iterator``
    """
    intrans = False
    inplural = False
    trimmed = False
    message_context = None
    singular = []
    plural = []
    lineno = 1
    comments = {}

    encoding = options.get('encoding', 'utf8')
    text = fileobj.read().decode(encoding)

    def _add_comment(lineno, comment):
        key = str(lineno)
        if (key in comments):
            comments[key].append(comment)
        else:
            comments[key] = [comment]

    def _get_comments(lineno):
        if lineno > 1:
            keys = [str(lineno), str(lineno - 1)]
        else:
            keys = [str(lineno)]

        string_comments = []
        for key in keys:
            if key in comments:
                string_comments.extend(comments[key])
        return string_comments

    try:
        text_lexer = Lexer(text)
    except TypeError:
        # Django 1.9 changed the way we invoke Lexer; older versions
        # require two parameters.
        text_lexer = Lexer(text, None)

    for t in text_lexer.tokenize():
        lineno += t.contents.count('\n')
        if intrans:
            if t.token_type == TOKEN_BLOCK:
                endbmatch = endblock_re.match(t.contents)
                pluralmatch = plural_re.match(t.contents)
                if endbmatch:
                    if inplural:
                        if message_context:
                            yield (
                                lineno,
                                'npgettext',
                                [smart_text(message_context),
                                 smart_text(join_tokens(singular, trimmed)),
                                 smart_text(join_tokens(plural, trimmed))],
                                _get_comments(lineno),
                            )
                        else:
                            yield (
                                lineno,
                                'ngettext',
                                (smart_text(join_tokens(singular, trimmed)),
                                 smart_text(join_tokens(plural, trimmed))),
                                _get_comments(lineno))
                    else:
                        if message_context:
                            yield (
                                lineno,
                                'pgettext',
                                [smart_text(message_context),
                                 smart_text(join_tokens(singular, trimmed))],
                                _get_comments(lineno),
                            )
                        else:
                            yield (
                                lineno,
                                None,
                                smart_text(join_tokens(singular, trimmed)),
                                _get_comments(lineno))

                    intrans = False
                    inplural = False
                    message_context = None
                    singular = []
                    plural = []
                elif pluralmatch:
                    inplural = True
                else:
                    raise SyntaxError('Translation blocks must not include '
                                      'other block tags: %s' % t.contents)
            elif t.token_type == TOKEN_VAR:
                if inplural:
                    plural.append('%%(%s)s' % t.contents)
                else:
                    singular.append('%%(%s)s' % t.contents)
            elif t.token_type == TOKEN_TEXT:
                if inplural:
                    plural.append(t.contents)
                else:
                    singular.append(t.contents)
        else:
            if t.token_type == TOKEN_BLOCK:
                imatch = inline_re.match(t.contents)
                bmatch = block_re.match(t.contents)
                cmatches = constant_re.findall(t.contents)
                if imatch:
                    g = imatch.group(1)
                    g = strip_quotes(g)
                    message_context = imatch.group(3)
                    if message_context:
                        # strip quotes
                        message_context = message_context[1:-1]
                        yield (
                            lineno,
                            'pgettext',
                            [smart_text(message_context), smart_text(g)],
                            _get_comments(lineno),
                        )
                        message_context = None
                    else:
                        yield lineno, None, smart_text(g), _get_comments(lineno)
                elif bmatch:
                    if bmatch.group(2):
                        message_context = bmatch.group(2)[1:-1]
                    for fmatch in constant_re.findall(t.contents):
                        stripped_fmatch = strip_quotes(fmatch)
                        yield lineno, None, smart_text(stripped_fmatch), _get_comments(lineno)
                    intrans = True
                    inplural = False
                    trimmed = 'trimmed' in t.split_contents()
                    singular = []
                    plural = []
                elif cmatches:
                    for cmatch in cmatches:
                        stripped_cmatch = strip_quotes(cmatch)
                        yield lineno, None, smart_text(stripped_cmatch), _get_comments(lineno)
            elif t.token_type == TOKEN_VAR:
                parts = t.contents.split('|')
                cmatch = constant_re.match(parts[0])
                if cmatch:
                    stripped_cmatch = strip_quotes(cmatch.group(1))
                    yield lineno, None, smart_text(stripped_cmatch), _get_comments(lineno)
                for p in parts[1:]:
                    if p.find(':_(') >= 0:
                        p1 = p.split(':', 1)[1]
                        if p1[0] == '_':
                            p1 = p1[1:]
                        if p1[0] == '(':
                            p1 = p1.strip('()')
                        p1 = strip_quotes(p1)
                        yield lineno, None, smart_text(p1), _get_comments(lineno)
            elif t.token_type == TOKEN_COMMENT:
                for comment_tag in comment_tags:
                    if comment_tag in t.contents:
                        _add_comment(lineno, t.contents)
