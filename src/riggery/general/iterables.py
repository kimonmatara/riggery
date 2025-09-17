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

def partial_reorder(items:Iterable, items_to_reorder:Iterable) -> list:
    """
    :param items: the full item list
    :param items_to_reorder: a sub-selection of elements from *items*, in the
        desired order
    :raises ValueError: Duplicate items in *items* or *items_to_reorder*.
    :raises ValueError: Some members of *items_to_reorder* are not members of
        *items*.
    :return: The members of *items*, reordered so that the subset of members in
        *items_to_reorder* is at the specified order, with the relative position
        of every other member preserved.
    """
    _items = set(items)
    _items_to_reorder = set(items_to_reorder)

    if len(_items) != len(items) or len(_items_to_reorder) != items_to_reorder:
        raise ValueError("Duplicate items")

    if not _items_to_reorder.issubset(_items):
        raise ValueError("Non-member items")

    head = items[:first_reord_index]
    middle = items_to_reorder
    tail = [x for x in items if x not in head + middle]
    return head + middle + tail