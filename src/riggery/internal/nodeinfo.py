from functools import cache
import re
import maya.cmds as m
import maya.api.OpenMaya as om

cap = lambda x: x[0].upper()+x[1:]
uncap = lambda x: x[0].lower()+x[1:]

UNCAPMAP = {} # capitalized: uncapitalized
NODETYPES = []

def _adjustNodeTypes(nodeTypes:list[str]):
    nodeTypes = list(filter(
        lambda x: x not in ('containerBase', 'entity', 'THdependNode'),
        nodeTypes
    ))
    return ['elem', 'dependNode'] + nodeTypes

@cache
def getPathFromNodeType(nodeType:str,
                        classNames:bool=True) -> list[str]:
    nodeTypes = m.nodeType(nodeType, isTypeName=True, inherited=True)
    nodeTypes = _adjustNodeTypes(nodeTypes)
    if classNames:
        nodeTypes = list(map(cap, nodeTypes))
    return nodeTypes

@cache
def getPathFromKey(clsname:str) -> list[str]:
    nodeType = UNCAPMAP[clsname]
    return getPathFromNodeType(nodeType, True)

def getKeyFromMObject(mObject:om.MObject) -> str:
    return cap(om.MFnDependencyNode(mObject).typeName)

def getPathFromMObject(mObject:om.MObject,
                       classNames:bool=True) -> list[str]:
    return getPathFromNodeType(
        om.MFnDependencyNode(mObject).typeName,
        classNames=classNames
    )

ABSTRACT_PAT = re.compile(r"^(.*?) \(abstract\)$")

def _start():
    global UNCAPMAP, NODETYPES

    for x in m.allNodeTypes(includeAbstract=True):
        mt = re.match(ABSTRACT_PAT, x)
        if mt:
            x = mt.groups()[0]
        NODETYPES.append(x)
        UNCAPMAP[cap(x)] = x

_start()