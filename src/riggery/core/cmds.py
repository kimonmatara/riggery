"""This is auto-populated with wrapped commands from maya.cmds on startup."""

from typing import Optional
from pathlib import Path
from .wrap import *
from ..general.functions import short
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