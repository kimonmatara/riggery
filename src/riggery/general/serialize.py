import collections.abc as _abc

def is_hashable(x) -> bool:
    try:
        hash(x)
        return True
    except TypeError:
        return False

def simplify(value):
    """
    Attempts to simplify *value* into some variant of a basic, JSON-supported
    type, such as int, float, list, dict etc.

    :raises TypeError: can't simplify value
    """
    if isinstance(value, (int, float, str)):
        return value

    if value is None:
        return None

    if isinstance(value, _abc.Mapping):
        return {simplify(k): simplify(v) for k, v in value.items()}

    if isinstance(value, (_abc.Iterable, _abc.Iterator)):
        return [simplify(member) for member in value]

    raise TypeError("can't simplify value")