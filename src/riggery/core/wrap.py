from functools import wraps

from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists
from .elem import Elem

import maya.cmds as m

#----------------------------------------------|
#----------------------------------------------|    GATHER
#----------------------------------------------|

def _conformToStr(item):
    if item is None:
        return None

    if isinstance(item, (tuple, list)):
        return type(item)([_conformToStr(member) for member in item])

    if isinstance(item, dict):
        return {k: _conformToStr(v) for k, v in item.items()}

    if isinstance(item, Elem):
        return str(item)

    return item

def _conformToElem(item):
    if item is None:
        return None

    if isinstance(item, (tuple, list)):
        return type(item)([_conformToElem(member) for member in item])

    if isinstance(item, dict):
        return {k: _conformToElem(v) for k, v in item.items()}

    try:
        return Elem(item)
    except:
        pass

    return item

def _wrapCmd(f):
    """
    :param cmdName: the name of the Maya command to wrap
    :raises AttributeError: The command is not available on
        :mod:`maya.cmds`.
    :return: The bongo-wrapped command.
    """
    @wraps(f)
    def wrapped(*args, **kwargs):
        args = _conformToStr(args)
        kwargs = _conformToStr(kwargs)
        return _conformToElem(f(*args, **kwargs))
    return wrapped

def _getWrappedCommands() -> dict:
    """
    :return: Every Maya command accessible via :mod:`maya.cmds`,
        wrapped to convert to and from :class:`~bongo.internal.Elem`
        instances.
    """
    out = {}
    for name in m.help('*', list=True):
        try:
            f = getattr(m, name)
        except AttributeError:
            continue
        out[name] = _wrapCmd(f)
    return out

def _installWrappedCmds():
    g = globals()
    wrapped = {k: v for k, v in _getWrappedCommands().items() \
               if k not in g}
    g.update(wrapped)
    g['__all__'] = list(wrapped.keys())

_installWrappedCmds()