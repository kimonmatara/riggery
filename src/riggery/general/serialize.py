from typing import Callable, Optional
import collections.abc as _abc

def is_hashable(x) -> bool:
    try:
        hash(x)
        return True
    except TypeError:
        return False

def simplify(value, handler:Optional[Callable]=None):
    """
    Attempts to simplify *value* into some variant of a basic, JSON-supported
    type, such as int, float, list, dict etc.

    :param handler: if provided, should be a callable that will receive *value*
        as its argument; this will be run first, and should throw
        :class:`TypeError` for any cases it doesn't cover; defaults to None
    :raises TypeError:
    """
    if handler is not None:
        try:
            return handler(value)
        except TypeError:
            pass

    if isinstance(value, (int, float, str)):
        return value

    if value is None:
        return None

    if isinstance(value, _abc.Mapping):
        return {simplify(k, handler): simplify(v, handler)
                for k, v in value.items()}

    if isinstance(value, (_abc.Iterable, _abc.Iterator)):
        return [simplify(member, handler) for member in value]

    raise TypeError("couldn't simplify {}".format(value))