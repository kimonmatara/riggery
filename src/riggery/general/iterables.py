"""General utilities for collections, iterables, lists etc."""

from typing import Iterable

def expand_tuples_lists(*items) -> list:
    """
    Flattens nested tuples and lists into a single list.
    """
    out = []

    for item in items:
        if isinstance(item, (tuple, list)):
            for member in item:
                out += expand_tuples_lists(member)
        else:
            out.append(item)

    return out

def pairiter(sequence):
    """
    Derived from PyMEL. Returns an iterator over every 2 items of *sequence*.
    """
    it = iter(sequence)
    return zip(it, it)

def without_duplicates(items:Iterable) -> list:
    """
    Returns a list copy of *items* with duplicates removed and order
    preserved.
    """
    out = []
    for item in items:
        if item not in out:
            out.append(item)
    return out

def crop_overlaps(groups):
    """
    Convenience function; returns a copy of *groups* where the last member is
    deleted on every group except the last one.
    """
    if len(groups) < 2:
        return list(groups)
    return [group[:-1] for group in groups[:-1]] + [groups[-1]]