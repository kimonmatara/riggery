"""Utilities for functions."""
from typing import Callable, Any
from functools import wraps
from pathlib import Path
import os
import json

def resolve_flags(*flags) -> tuple:
    """
    Evaluates flags Maya-style. If one flag is True and the rest are None,
    the rest are evaluated as False, and so on.

    :param *flags: The flags to resolve.
    :return: The resolved flags.
    """
    flags = [None if flag is None else bool(flag) for flag in flags]
    if flags.count(True):
        flags = [False if flag is None else flag for flag in flags]
    elif flags.count(False):
        flags = [True if flag is None else flag for flag in flags]
    else:
        flags = [True] * len(flags)
    return tuple(flags)

def conform_multi_arg(arg, length:int=0) -> list[Any]:
    """
    :param arg: a list, tuple, or single input argument
    :param length: the length of the list that *arg* should be conformed to
    :raises ValueError: *arg* is a list of tuple, with a length that is neither
        1 nor matches *length*
    :return: A list of arguments of the specified *length*.
    """
    if length < 1:
        return arg
    if isinstance(arg, (tuple, list)):
        num = len(arg)
        if num == length:
            return list(arg)
        if num == 0:
            return list(arg) * length
        raise ValueError("Wrong argument length")
    return [arg] * length

class short:
    """
    Decorator with keyword arguments, used to mimic Maya's 'shorthand'
    flags.

    :Example:

        .. code-block:: python

            @short(numJoints='nj')
            def makeJoints(numJoints=16):
                [...]

            # This can then be called as:
            makeJoints(nj=5)
    """
    def __init__(self, **mapping):
        self.mapping = mapping
        self.reverse_mapping = {v:k for k, v in mapping.items()}

    def __call__(self, f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            resolved = {}

            for k, v in kwargs.items():
                k = self.reverse_mapping.get(k,k)
                resolved[k] = v

            return f(*args, **resolved)

        wrapper.__shorthands__ = self.mapping

        return wrapper