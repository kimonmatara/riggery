import os
from pathlib import Path
from tempfile import gettempdir
from typing import Literal

import maya.cmds as m
import maya.mel as mel
from riggery.general.iterables import expand_tuples_lists, without_duplicates
from riggery.general.functions import short

from .selection import keepsel

mel.eval('source MLdeleteUnused')

#-------------------------------------------------|
#-------------------------------------------------|    Errors
#-------------------------------------------------|

class CleanupError(RuntimeError):
    pass

#-------------------------------------------------|
#-------------------------------------------------|    Unknown nodes
#-------------------------------------------------|

def getUnknownNodes():
    out = m.ls(type='unknown')
    if out:
        return out
    return []

def removeUnknownNode(node):
    if m.objExists(node):
        if m.referenceQuery(node, isNodeReferenced=True):
            raise CleanupError(
                "Can't remove referenced unknown node: {}".format(node)
            )

        m.lockNode(node, lock=False)
        m.delete(node)
        print("Deleted unknown node: {}".format(node))

def removeUnknownNodes(*nodes, skipErrors=False):
    nodes = without_duplicates([str(x) for x in expand_tuples_lists(*nodes)])

    if not nodes:
        nodes = getUnknownNodes()

    removed = []

    for node in nodes:
        try:
            removeUnknownNode(node)
            removed.append(node)

        except Exception as exc:
            if skipErrors:
                continue
            raise CleanupError(str(exc))

    return removed

#-------------------------------------------------|
#-------------------------------------------------|    Unknown plugins
#-------------------------------------------------|

def getUnknownPlugins():
    out = m.unknownPlugin(q=True, list=True)

    if out:
        return out

    return []

def removeUnknownPlugin(plugin):
    m.unknownPlugin(plugin, remove=True)

def removeUnknownPlugins(*plugins, skipErrors=False):
    plugins = list(without_duplicates(expand_tuples_lists(*plugins)))

    if not plugins:
        plugins = getUnknownPlugins()

    removed = []

    for plugin in plugins:
        try:
            removeUnknownPlugin(plugin)
            removed.append(plugin)
        except Exception as exc:
            if skipErrors:
                continue
            raise CleanupError(str(exc))

    return removed

#-------------------------------------------------|
#-------------------------------------------------|    Unused shaders
#-------------------------------------------------|

def removeUnusedShaders():
    """
    Currently a thin wrapper around Maya's 'Delete Unused Nodes' Hypershade
    command, may break if Autodesk changes the MEL codebase.
    """
    mel.eval('MLdeleteUnused')

#-------------------------------------------------|
#-------------------------------------------------|    Stripdown
#-------------------------------------------------|

@keepsel
def stripdown(*nodes) -> list[str]:
    """
    :raises ValueError: no nodes specified
    :return: The resolved partial DAG paths.
    """
    sceneName = m.file(sceneName=True, q=True)
    nodes = list(without_duplicates(map(str, expand_tuples_lists(*nodes))))

    if not nodes:
        raise ValueError('No nodes specified')

    tmpDir = Path(gettempdir())
    index = 0

    while True:
        basename = 'mayaStripDownTmp'
        if index > 0:
            basename += '_'+str(index)
        filename = basename + '.mb'
        filepath = tmpDir / filename

        if filepath.is_file():
            index += 1
            continue
        break

    m.select(nodes, replace=True, noExpand=True)

    m.file(filepath.as_posix(),
           force=True,
           options='v=0;',
           typ='mayaBinary',
           es=True)

    m.file(newFile=True, force=True)

    if sceneName:
        m.file(rename=sceneName)

    m.file(filepath.as_posix(),
           i=True,
           typ='mayaBinary',
           ignoreVersion=True,
           mergeNamespacesOnClash=False,
           rpr='stripdown',
           options='v=0;',
           pr=True)

    os.remove(filepath)

    out = []

    for node in nodes:
        matches = m.ls(node)
        numMatches = len(matches)

        if numMatches > 0:
            out.append(matches[0])
        else:
            if '|' in node:
                node = node.split('|')[-1]
                matches = m.ls(node)
                numMatches = len(matches)

                if numMatches > 0:
                    out.append(matches[0])
    return out

#-------------------------------------------------|
#-------------------------------------------------|    I/O
#-------------------------------------------------|

@short(namespace='ns')
def openScene(path,
              mode:Literal[0, 1, 2, 'open', 'import', 'reference']=0,
              namespace=None):

    print("Incoming mode: ", mode)

    if isinstance(mode, str):
        mode = ['open', 'import', 'reference'].index(mode)

    path = Path(path)
    kwargs = {'f': True, 'options':'v=0;', 'ignoreVersion':True}

    if mode == 0:
        kwargs['o'] =True

    elif mode == 1:
        kwargs['i'] = False
        kwargs['pr'] = True

        if namespace:
            kwargs['namespace'] = namespace
            kwargs['mergeNamespacesOnClash'] = False

        else:
            kwargs['rpr'] = path.stem

    elif mode == 2:
        if not namespace:
            namespace = path.stem
        kwargs['namespace'] = namespace
        kwargs['gl'] = True
        kwargs['mergeNamespacesOnClash'] = False
        kwargs['r'] = True

    else:
        raise ValueError('Invalid mode')

    out = m.file(path.as_posix(), **kwargs)

    if mode == 2:
        out = m.referenceQuery(out, referenceNode=True)

    return out