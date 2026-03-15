"""Utilities for functions."""
import inspect
from types import FunctionType
from functools import wraps
from typing import Callable, Any, Optional, Literal, Iterator, get_type_hints
from warnings import warn
from .types import conform_instance


class Callbacks:
    def __init__(self, errorLevel:Literal[0, 1, 2]=2):
        """
        :param errorLevel: if 0, completely hide errors; if 1, show a warning;
            if 2, raise exceptions; defaults to 2
        """
        self._callbacks = set()
        self._errorLevel = errorLevel

    def add(self, callback:Callable):
        self._callbacks.add(callback)

    def remove(self, callback:Callable):
        self._callbacks.remove(callback)

    def clear(self):
        self._callbacks.clear()

    def __bool__(self):
        return len(self._callbacks) > 0

    def __len__(self):
        return len(self._callbacks)

    def __iter__(self):
        yield from self._callbacks

    def __call__(self, *args, **kwargs):
        for cb in self._callbacks:
            try:
                cb(*args, **kwargs)
            except Exception as exc:
                if self._errorLevel == 2:
                    raise exc
                elif self._errorLevel == 1:
                    warn(f"Callback failed: {exc}")

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

def get_long_kwargs(kwargs:dict, shorthands:dict) -> dict:
    rshorts = {v:k for k, v in shorthands.items()}
    return {rshorts.get(k, k): v for k, v in kwargs.items()}

def get_short_kwargs(kwargs:dict, shorthands:dict) -> dict:
    return {shorthands.get(k, k): v for k, v in kwargs.items()}

def get_shorthands(f:FunctionType, recurse:bool=False) -> dict:
    """
    If no shorthands are discovered at all, an empty dict will be returned. You
    may get unexpected results if any of the decorators in the stack don't use
    @wraps.

    :param recurse: if there are multiple @short decorators, dig down to the
        innermost one and update the returned dictionary in reverse order;
        defaults to False
    """
    if not inspect.isfunction(f):
        raise TypeError(f"not a function: {f}")

    if recurse:
        shorthand_dicts = []
        current = f

        while True:
            try:
                shorthand_dicts.append(current.__shorthands__)
            except AttributeError:
                pass

            current = getattr(current, '__wrapped__', None)

            if current is None:
                break

        out = {}

        for d in reversed(shorthand_dicts):
            out.update(d)

        return out
    else:
        return getattr(f, '__shorthands__', {})

def unwrap(f:FunctionType) -> Optional[FunctionType]:
    """
    Caution: this only works if the decorator itself used @wraps internally.
    """
    return getattr(f, '__wrapped__', None)

def iter_unwrap(f:FunctionType) -> Iterator[FunctionType]:
    """
    Returns internal functions; *f* itself is skipped. Caution: this won't work
    if decorators didn't use @wraps.
    """
    current = f

    while True:
        current = getattr(current, '__wrapped__', None)

        if current is None:
            break
        yield current

class lazy_property:
    """
    Alternative to property that works with name lookups, so that you don't have
    to re-declare properties in subclasses every time you override one of their
    getter / setter / deleter methods.
    """
    def __init__(self,
                 fget:Optional[str]=None,
                 fset:Optional[str]=None,
                 fdel:Optional[str]=None):
        self._fget = fget
        self._fset = fset
        self._fdel = fdel

    def __get__(self, inst, instype):
        if self._fget:
            meth = getattr(inst, self._fget)
            return meth()
        raise AttributeError("can't get attribute")

    def __set__(self, inst, value):
        if self._fset:
            meth = getattr(inst, self._fset)
            return meth(value)
        raise AttributeError("can't set attribute")

    def __delete__(self, inst):
        if self._fdel:
            meth = getattr(inst, self._fdel)
            return meth()
        raise AttributeError("can't delete attribute")

def cast_params(f):
    """
    Decorator. Attempts to cast any received args / kwargs to their type hints
    before passing them along to the wrapped function.
    """
    signature = inspect.signature(f)

    pos_only = []
    pos_or_kw = []

    for param_name, param in signature.parameters.items():
        if param.kind == inspect.Parameter.POSITIONAL_ONLY:
            pos_only.append(param_name)

        elif param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD:
            pos_or_kw.append(param_name)

    hints = get_type_hints(f)

    @wraps(f)
    def wrapper(*args, **kwargs):
        _pos_only = pos_only.copy()
        _pos_or_kw = pos_or_kw.copy()

        out_args = []

        for arg in args:
            try:
                name = _pos_only.pop(0)
            except IndexError:
                try:
                    name = _pos_or_kw.pop(0)
                except IndexError:
                    out_args.append(arg)
                    continue

                try:
                    hint = hints[name]
                except KeyError:
                    out_args.append(arg)
                    continue

                out_args.append(conform_instance(arg, hint, False, True))

        out_kwargs = {}

        for k, v in kwargs.items():
            try:
                hint = hints[k]
            except KeyError:
                out_kwargs[k] = v
                continue

            out_kwargs[k] = conform_instance(v, hint, False, True)

        return f(*out_args, **out_kwargs)
    return wrapper