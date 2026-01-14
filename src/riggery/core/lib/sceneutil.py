import maya.cmds as m
import maya.mel as mel
from riggery.general.iterables import expand_tuples_lists, without_duplicates

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