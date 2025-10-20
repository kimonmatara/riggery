"""General utilities for collections, iterables, lists etc."""

from typing import Iterable, Any, Generator

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

def without_duplicates(items:Iterable) -> Generator[Any, None, None]:
    """
    Yields members of *items* only once, in order.
    """
    out = set()

    for item in items:
        if item not in out:
            out.add(item)
            yield item

def crop_overlaps(groups):
    """
    Convenience function; returns a copy of *groups* where the last member is
    deleted on every group except the last one.
    """
    if len(groups) < 2:
        return list(groups)
    return [group[:-1] for group in groups[:-1]] + [groups[-1]]

def issublist(sublist:list, containerlist:list) -> bool:
    """
    :return: True if *containerlist* contains *sublist* in the same sequence.
    """
    try:
        startIndex = containerlist.index(sublist[0])
    except ValueError:
        return False

    try:
        endIndex = containerlist.index(sublist[-1])
    except ValueError:
        return False

    contained_segment = containerlist[startIndex:endIndex+1]
    if len(sublist) == len(contained_segment):
        return all((x==y for x, y in zip(sublist, contained_segment)))
    return False

def fill_nones_with_chase(lst:list) -> None:
    """
    Replaces each None value in a list by re-using the last non-None value
    preceding it or, failing that, the first non-None value following it.

    This is an in-place operation. This function has no return.
    """
    out = []
    last_not_none = None

    for item in lst:
        if item is None:
            item = last_not_none
        else:
            last_not_none = item
        out.append(item)

    out.reverse()
    out2 = []

    for item in out:
        if item is None:
            item = last_not_none
        else:
            last_not_none = item
        out2.append(item)
    lst[:] = reversed(out2)