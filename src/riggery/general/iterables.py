"""General utilities for collections, iterables, lists etc."""

from itertools import islice
from typing import Iterable, Any, Iterator

def expand_tuples_lists(*items, keep_tuples:bool=False) -> list:
    """
    Flattens nested tuples and lists into a single list.
    """
    out = []

    for item in items:
        if isinstance(item, tuple):
            if keep_tuples:
                out.append(item)
            else:
                for member in item:
                    out += expand_tuples_lists(member, keep_tuples=False)
        elif isinstance(item, list):
            for member in item:
                out += expand_tuples_lists(member, keep_tuples=keep_tuples)
        else:
            out.append(item)

    return out

def pairiter(sequence):
    """
    Derived from PyMEL. Returns an iterator over every 2 items of *sequence*.
    """
    it = iter(sequence)
    return zip(it, it)

def without_duplicates(items:Iterable,
                       fast:bool=True) -> Iterator[Any]:
    """
    Yields members of *items* only once, in order.

    :param fast: set this to False if you expect unhashable types; defaults to
        True
    """
    if fast:
        out = set()

        for item in items:
            if item not in out:
                out.add(item)
                yield item
    else:
        out = []

        for item in items:
            if item not in out:
                out.append(item)
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

def overlapping_pairs(iterable:Iterable) -> Iterator[tuple]:
    """
    Takes something like: [1, 2, 3, 4]
    Returns something like: [[1, 2], [2, 3], [3, 4]]
    """
    elems = list(iterable)
    return zip(elems, elems[1:])

def pad_nones(items:list, conserve:bool=True) -> list:
    """
    Replaces any None members with the nearest non-None member.

    :param conserve: if this is True, then, at each iteration, the last non-None
        value will be retained unless there is only one looking forwards

    :raises ValueError: need at least two members
    :raises ValueError: all the items are already None
    """
    out = []
    items = list(items)

    numNones = items.count(None)

    if numNones == 0:
        return items

    numItems = len(items)

    if numNones == numItems:
        raise ValueError("all items are None")

    for i, item in enumerate(items):
        if item is None:
            if conserve and i > 0 and out[-1] is not None:
                item = out[-1]
            else:
                closestDelta = None
                closestMember = None

                if backward:
                    # Look backwards
                    if i > 0:
                        for x in reversed(range(i)):
                            candidate = items[x]
                            if candidate is not None:
                                closestDelta = i-x
                                closestMember = candidate
                                break

                if forward:
                    # Look forwards
                    if i < numItems - 1:
                        for x in range(i+1, numItems):
                            candidate = items[x]
                            if candidate is not None:
                                delta = x - i
                                if closestDelta is None or delta < closestDelta:
                                    closestDelta = delta
                                    closestMember = candidate
                                    break
                item = closestMember
        out.append(item)

    return out

def chunks(iterable, n) -> Iterator[list]:
    it = iter(iterable)

    while chunk := list(islice(it, n)):
        yield chunk

def check_index(index:int, length:int, positive:bool=False) -> int:
    """
    Simple index checker.

    :param index: the index to check
    :param length: the length of the list
    :param positive: reject negative indices; defaults to False
    :raises IndexError: The index is outside the allowed range.
    :return: The unmodified index.
    """
    if index >= 0:
        if index < length:
            return index
        raise IndexError('index out of range')
    else:
        if positive:
            raise IndexError('negative indices not supported')
        if index > -length - 1:
            return index
        else:
            raise IndexError('index out of range')