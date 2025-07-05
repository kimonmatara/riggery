"""
Warning: none of the routines in this module perform MObject validation. Make
sure instances are valid beforehand.
"""

from typing import Optional, Union
import maya.api.OpenMaya as om

def getNodeBasename(mObject:om.MObject) -> str:
    """
    Fast implementation if you just want a node's basename and don't care
    about DAG information.

    :param mObject: a :class:`~maya.api.OpenMaya.MObject` instance for the
        node
    :param safe: checks that the :class:`~maya.api.OpenMaya.MObject` is valid
        (recommended); defaults to ``True``
    :return: The node's basename.
    """
    return om.MFnDependencyNode(mObject).name()

def fromNodeBundle(
        dagPath:Optional[om.MDagPath],
        mObject:om.MObject, *,
        isDagNode:Optional[bool]=None
) -> str:
    """
    .. warning::
        If you don't have a DAG path, and the node is an instanced DAG node,
        you'll get the path to the first instance.

    :param dagPath: a :class:`~maya.api.OpenMaya.MDagPath` instance, or None
        if it's not a DAG node, or if a DAG path is not available
    :param mObject: a :class:`~maya.api.OpenMaya.MObject` instance
    :param isDagNode: if you already know whether this is a DAG object
        (or not), specify it here to save a check; defaults to None
    :return: If a DAG node, the shortest disambiguating path; otherwise,
        the node name.
    """
    if isDagNode is None:
        isDagNode = dagPath is not None or mObject.hasFn(om.MFn.kDagNode)

    if isDagNode:
        if dagPath is None:
            inst = om.MFnDagNode(mObject)
            return inst.partialPathName()
        return dagPath.partialPathName()

    inst = om.MFnDependencyNode(mObject)
    return inst.name()

def fromNodeMObject(mObject:om.MObject, *,
                    isDagNode:Optional[None]=None) -> str:
    """
    Use this if you don't know whether a node is a DAG node or not,
    or you don't have a DAG path.

    .. warning::
        If you don't have a DAG path, and the node is an instanced DAG node,
        you'll get the path to the first instance.

    :param mObject: a :class:`~maya.api.OpenMaya.MObject` instance
    :param isDagNode: if you know whether *mObject* is a DAG node or not,
        specify it here to skip a check; defaults to ``None``
    :return: A short unambiguous path to the node, or just the basename if
        it's not a DAG node.
    """
    if isDagNode is None:
        isDagNode = mObject.hasFn(om.MFn.kDagNode)

    if isDagNode:
        return om.MFnDagNode(mObject).partialPathName()
    return om.MFnDependencyNode(mObject).name()

def fromNodeMDagPath(dagPath:om.MDagPath) -> str:
    """
    :param dagPath: an :class:`~maya.api.OpenMaya.MDagPath` to a node
    :return: A partial unambiguous path string to the DAG node.
    """
    return dagPath.partialPathName()

def fromComponentBundle(dagPath:om.MDagPath, mObject:om.MObject) -> str:
    """
    :param dagPath: an :class:`~maya.api.OpenMaya.MDagPath` to the owner node
    :param mObject: an :class:`~maya.api.OpenMaya.MObject` instance for the
        component
    :return: A partial unambiguous path string to the component.
    """
    return om.MSelectionList().add(
        (dagPath, mObject)
    ).getSelectionStrings()[0]

def fromMPlug(mPlug:om.MPlug) -> str:
    """
    :param mPlug: a :class:`~maya.api.OpenMaya.MPlug` instance for the
        attribute
    :return: A partial unambiguous path string to the attribute.
    """
    node = mPlug.node()
    if node.hasFn(om.MFn.kDagNode):
        _node = om.MFnDagNode(node).partialPathName()
    else:
        _node = om.MFnDependencyNode(node).name()

    _plug = mPlug.partialName(includeNodeName=False,
                             includeInstancedIndices=True,
                             useLongNames=True)
    return f"{_node}.{_plug}"