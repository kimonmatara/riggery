import re
from string import ascii_uppercase

def uncap(s:str) -> str:
    """
    Uncapitalizes the first letter of *s*, but only if it's not followed by
    another capital letter.
    """
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