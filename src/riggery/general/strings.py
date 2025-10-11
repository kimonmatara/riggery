"""General string utilities."""

import re
from string import ascii_uppercase

def cap(s:str) -> str:
    """
    Capitalizes the first letter of *s*.
    """
    if s:
        return s[0].upper() + s[1:]
    return

def uncap(s:str) -> str:
    """
    Uncapitalizes the first letter of *s*, but only if it's not followed by
    another capital letter.
    """
    if s:
        def replacer(x):
            start, end = x.span()
            orig = x.string[start:end]
            return orig.lower()

        s = re.sub(r"(?<=^)[A-Z](?![A-Z])", replacer, s)
    return s

def int_to_letter(number:int, start:int=0) -> str:
    """
    Converts an integer index into a letter. More letters are added every
    time the alphabetic range runs out.

    :param number: the integer to convert
    :param start: the number to start numbering from; if you want 1 to be 'A'
        rather than 0, set this to 1; defaults to 0
    :return: The letter index.
    """
    number -= start
    return ascii_uppercase[number % 26] * ((number // 26)+1)

def split_camel(s):
    """
    Simple camelcase splitter. Ignores numbers.

    :param s: the string to split
    :return: The resulting words.
    """
    if s:
        origChars = list(s)
        groups = [[origChars[0]]]

        for i, thisChar in enumerate(origChars[1:], start=1):
            prevChar = origChars[i-1]

            if thisChar.isupper() and prevChar.islower():
                groups.append([thisChar])
            else:
                groups[-1].append(thisChar)

        return [''.join(group) for group in groups]

    return s

def split_multi(s, delims):
    """
    Recursively splits a string using multiple delimiters or callables.

    :param s: the string to split
    :param delims: the list of delimiters to use; this can include
        callables, for example :func:`split_camel`
    :return: A list of string elements.
    """
    out = [s]

    for delim in delims:
        new_elems = []

        if callable(delim):
            for item in out:
                new_elems += delim(item)
        else:
            for item in out:
                new_elems += item.split(delim)

        out = new_elems

    return out

def nice_name(name:str) -> str:
    """
    Splits by camel and underscores, capitalizes, joins with spaces.
    """
    elems = split_multi(name, [' ', '_', split_camel])
    elems = [cap(elem) for elem in elems if elem]
    return ' '.join(elems)