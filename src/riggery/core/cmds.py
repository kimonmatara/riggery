"""This is auto-populated with wrapped commands from maya.cmds on startup."""

from typing import Optional, Iterable, Iterator
from pathlib import Path
from .wrap import *
from ..general.functions import short
from ..general.iterables import without_duplicates
from .nodetypes import __pool__ as _nodes
import maya.cmds as m

def openScene(path) -> None:
    path = Path(path)
    # Not including the long type, as I've run into some weirdness
    m.file(path.as_posix(),
           ignoreVersion=True,
           o=True,
           f=True,
           prompt=False,
           options='v=0;')

@short(namespace='ns')
def importScene(path, namespace:Optional[str]=None) -> None:
    path = Path(path)
    # longType = {'.ma': 'mayaAscii', '.mb': 'mayaBinary'}[path.suffix]
    kwargs = {}

    if namespace:
        kwargs['namespace'] = namespace
    else:
        kwargs['rpr'] = path.stem

    m.file(path.as_posix(),
           i=True,
           # typ=longType,
           f=True,
           prompt=False,
           options='v=0;',
           ignoreVersion=True,
           mergeNamespacesOnClash=False,
           pr=True,
           **kwargs)

@short(namespace='ns')
def referenceScene(path, namespace:Optional[str]=None) -> '_nodes.Reference':
    path = Path(path)
    # longType = {'.ma': 'mayaAscii', '.mb': 'mayaBinary'}[path.suffix]

    if not namespace:
        namespace = path.stem

    result = m.file(path.as_posix(),
                    r=True,
                    # typ=longType,
                    prompt=False,
                    options='v=0;',
                    ignoreVersion=True,
                    ns=namespace,
                    gl=True,
                    mergeNamespacesOnClash=False)

    return _nodes['Reference'](m.referenceQuery(result, referenceNode=True))

def iterExpandLookups(*lookups:str,
                      type:Optional[str|Iterable[str]]=None) -> Iterator['_nodes.DependNode']:
    """
    Yields nodes.

    :param lookups: one or more lookups for ``ls``
    :param type: one or more optional type filters; defaults to None
    """
    kwargs = {}
    if type is not None:
        if isinstance(type, str):
            kwargs['typ'] = type
        else:
            kwargs['typ'] = list(without_duplicates(type))

    visited = set()

    for lookup in map(str, lookups):
        matches = m.ls(lookup, **kwargs)
        for match in matches:
            if match in visited:
                continue
            visited.add(match)
            yield _nodes['DependNode'](match)