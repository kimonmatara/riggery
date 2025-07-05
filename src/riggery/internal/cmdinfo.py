import inspect
from typing import Callable, Optional, Union
import re

from functools import cache
from riggery.general.iterables import expand_tuples_lists
from riggery.general.functions import short
from .typeutil import UNDEFINED

import maya.cmds as m


@cache
def getFlagInfo(cmdName:str) -> list[dict]:
    """
    Returns information for each 'flag' (keyword) argument on a Maya command.
    """
    help = m.help(cmdName)
    out = []

    for line in help.split('\n'):
        line = line.strip()
        if line:
            pat = r"\-\S+"
            elems = re.findall(pat, line)

            if elems:
                elems = [re.match(r"^\-(.*)$", e).groups()[0] for e in elems]

            num = len(elems)
            if num > 0:
                info = {}
                if num == 1:
                    info['name'] = elems[0]
                else:
                    info['shortName'], info['name'] = elems[0], elems[1]
                out.append(info)
    return out

class useCmdFlags:
    """
    Decorator-with-arguments. Adds keywords (including shorthands) from a
    named Maya command.
    """
    def __init__(self, cmdName:str, skip:Union[str, list[str], None]=None):
        self._cmdName = cmdName
        self._skip = expand_tuples_lists(skip) if skip else []

    def __call__(self, f:Callable):
        flagInfo = getFlagInfo(self._cmdName)

        signature = inspect.signature(f)
        newParams = {k: v for k, v in signature.parameters.items() \
                     if v.kind != inspect.Parameter.VAR_KEYWORD}
        shorts = {}

        for entry in flagInfo:
            name = entry['name']
            if name in newParams or name in self._skip:
                continue
            try:
                shorts[name] = entry['shortName']
            except KeyError:
                pass
            newParams[name] = inspect.Parameter(
                name,
                inspect.Parameter.KEYWORD_ONLY,
                default=UNDEFINED
            )

        def wrapper(*args, **kwargs):
            outKwargs = {}
            for k, v in kwargs.items():
                if k in newParams:
                    if v is not UNDEFINED:
                        outKwargs[k] = v
                else:
                    raise ValueError(f"Unexpected argument: '{k}'")

            return f(*args, **outKwargs)

        signature = signature.replace(parameters=tuple(newParams.values()))
        wrapper.__signature__ = signature
        wrapper.__wrapped__ = f
        wrapper.__name__ = f.__name__
        wrapper.__qualname__ = f.__qualname__

        if shorts:
            wrapper = short(**shorts)(wrapper)

        return wrapper