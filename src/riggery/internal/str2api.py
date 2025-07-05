from traceback import format_exc
from typing import Union, Optional
import re
import maya.api.OpenMaya as om
import maya.cmds as m

#-------------------------------------------|
#-------------------------------------------|    ERRORS
#-------------------------------------------|

class Str2ApiError(RuntimeError):
    """Unspecified object-retrieval error."""

class Str2ApiNoMatchError(Str2ApiError):
    """No scene matches for the specified string lookup."""

class Str2ApiBadLookupError(Str2ApiError):
    """Malformed lookup string."""

class Str2ApiTypeError(Str2ApiError):
    """The lookup does not refer to an object of the expected type."""

#-------------------------------------------|
#-------------------------------------------|    NODES
#-------------------------------------------|

def getMDagPath(lookup:str) -> om.MDagPath:
    """
    Note that, if *lookup* is a path to a component, a DAG path will be
    returned the owner node.

    :param lookup: the string representation of the DAG path
    :raises Str2ApiNoMatchError: No match found (or not unique).
    :raises Str2ApiTypeError: Not a path to a node or component.
    :return: An :class:`~maya.api.OpenMaya.MDagPath` for the given string
        lookup.
    """
    try:
        return om.MSelectionList().add(lookup).getDagPath(0)
    except RuntimeError as exc:
        _exc = str(exc)
        if 'Object does not exist' in _exc:
            raise Str2ApiNoMatchError(lookup)
    except TypeError as exc:
        _exc = str(exc)
        if 'item is not a DAG' in _exc:
            raise Str2ApiTypeError(lookup)
        raise exc

def getNodeMObject(lookup:str) -> om.MObject:
    """
    Use this instead of :func:`getNodeBundle` if you just need the
    :class:`~maya.api.OpenMaya.MObject` and don't care about DAG information.

    :param lookup: an unambiguous path to a dependency node; note that, if
        *lookup* instead refers to an existing attribute or component, the
        owner node will be returned
    :return: A :class:`~maya.api.OpenMaya.MObject` instance for the node.
    """
    sel = om.MSelectionList()
    try:
        sel.add(lookup)
    except RuntimeError as exc:
        _exc = str(exc)
        if 'Object does not exist' in _exc:
            raise Str2ApiNoMatchError(lookup)
        raise Str2ApiError(lookup)

    return sel.getDependNode(0)

def getNodeBundle(
        lookup:str,
        isDagNode:Optional[bool]=None
) -> Union[Optional[om.MDagPath], om.MObject]:
    """
    :param lookup: an unambiguous path to a DAG or non-DAG node; note that, if
        *lookup* instead refers to an existing attribute or component, the
        owner node will be returned
    :param isDagNode: pass ``True`` or ``False`` here if you already know
        whether to expect a DAG node, and want to save on a check or throw
        an exception if it's not a DAG node; defaults to ``None``
    :raises Str2ApiTypeError: The lookup does not refer to a node.
    :raises Str2ApiBadLookupError: Wonky lookup string.
    :raises Str2ApiNoMatchError: No matches found for the lookup (or
        not unique).
    :return: Tuple of :class:`~maya.api.OpenMaya.MDagPath` (or None, if not a
        DAG node) and :class:`~maya.api.OpenMaya.MObject`.
    """
    sel = om.MSelectionList()

    try:
        sel.add(lookup)
    except RuntimeError as exc:
        _exc = str(exc)
        if 'Object does not exist' in _exc:
            raise Str2ApiNoMatchError(lookup)
        raise Str2ApiError(lookup)

    mObject = sel.getDependNode(0)

    if isDagNode is None:
        isDagNode = mObject.hasFn(om.MFn.kDagNode)

    if isDagNode:
        try:
            dagPath = sel.getDagPath(0)
        except TypeError as exc:
            _exc = str(exc)
            if "not a DAG" in _exc:
                raise Str2ApiTypeError(
                    f"Not a path to a DAG node: '{lookup}'"
                )
            raise Str2ApiError(lookup)
        except Exception:
            raise Str2ApiError(lookup)
    else:
        dagPath = None

    return dagPath, mObject

#-------------------------------------------|
#-------------------------------------------|    PLUGS
#-------------------------------------------|

def getMPlug(lookup:str, *,
             firstElem:bool=False,
             checkShape:bool=True,
             checkIsPlug:bool=False) -> om.MPlug:
    """
    :param path: the full path to an attribute
    :param firstElem: if the attribute is a multi, automatically expand to
        logical element 0; defaults to False
    :param checkShape: if the node is a transform, look for the attribute on
        its shape too; defaults to True
    :param checkIsPlug: Maya will quietly return an invalid MPlug if *lookup*
        refers to an existing node (and not an attribute); pass ``True`` here
        to check for this; defaults to ``False``
    :return: An :class:`~maya.api.OpenMaya.MPlug` reference to the attribute.
    """
    # Split in every case to catch bad references
    try:
        node, ext = lookup.split('.', 1)
    except ValueError:
        raise Str2ApiBadLookupError(
            f"Invalid attribute lookup: {lookup}"
        )
    if (node and ext):
        if checkShape and firstElem: # faster implementation
            sel = om.MSelectionList()
            try:
                sel.add(lookup)
            except RuntimeError as exc:
                _exc = str(exc)
                if 'Object does not exist' in _exc:
                    raise Str2ApiNoMatchError(lookup)
                raise Str2ApiError(lookup)
            out = sel.getPlug(0)
            if checkIsPlug:
                try:
                    out.attribute()
                except RuntimeError as exc:
                    _exc = str(exc)
                    if "Unexpected Internal Failure" in _exc:
                        raise Str2ApiTypeError(f"Not an attribute: {lookup}")
                    raise Str2ApiTypeError(lookup)
            return out
        else:
            nodeMObject = getNodeMObject(node)
            return getMPlugOnNode(nodeMObject, ext,
                                  firstElem=firstElem, checkShape=checkShape)
    else:
        raise Str2ApiTypeError(
            f"Invalid attribute lookup: {lookup}"
        )

def getMPlugOnNode(node:om.MObject,
                   extension:str,
                   firstElem:bool=False,
                   checkShape:bool=True) -> om.MPlug:
    """
    .. warning::
        Doesn't check if *node* is a valid
        :class:`~maya.api.OpenMaya.MObject`.

    :param node: the node with the attribute
    :param extension: the local path to the attribute (e.g.
        ``.input3D[0].input3Dx``)
    :param firstElem: if the attribute is a multi, automatically expand to
        logical element 0; defaults to False
    :param checkShape: if the node is a transform, look for the attribute on
        its shape too; defaults to True
    :raises Str2ApiNoMatchError: The requested attribute couldn't be
        retrieved.
    :return: An :class:`~maya.api.OpenMaya.MPlug` reference to the attribute
        on the node.
    """
    nodeFn = om.MFnDependencyNode(node)
    plug = multi = index = None

    try:
        for elem in filter(bool, re.split(r"\[(.*?)\]|\.", extension)):
            if elem.isdigit():
                index = int(elem)
                plug = plug.elementByLogicalIndex(index)
                multi = plug
            else:
                try:
                    plug = nodeFn.findPlug(elem, False)
                except RuntimeError as exc:
                    raise Str2ApiNoMatchError(extension)
                if index is not None:
                    plug.selectAncestorLogicalIndex(
                        index,
                        attribute=multi.attribute()
                    )
        if firstElem and plug.isArray:
            plug = plug.elementByLogicalIndex(0)
    except Exception as exc:
        if checkShape and node.hasFn(om.MFn.kTransform):
            mfn = om.MFnDagNode(node)
            children = [mfn.child(i) for i in range(mfn.childCount())]

            if children:
                children = list(
                    sorted(
                        children,
                        key=lambda x: om.MFnDagNode(x).isIntermediateObject
                    )
                )
                return getMPlugOnNode(children[0],
                                      extension,
                                      firstElem=firstElem)
        raise Str2ApiNoMatchError(extension)

    return plug

def getArrayContext(mPlug) -> Optional[tuple[int, om.MObject]]:
    """
    :return: The index of the array this MPlug belongs to, and the array itself
        as an MObject.
    """
    current = mPlug
    while True:
        if current.isElement:
            return current.logicalIndex(), current.attribute()
        elif current.isChild:
            current = current.parent()
        else:
            break

def getMPlugOnMPlug(thisMPlug, attrName):
    node = thisMPlug.node()
    nodeFn = om.MFnDependencyNode(node)
    attr = nodeFn.attribute(attrName)

    outMPlug = om.MPlug(node, attr)

    # Look for multi context
    ctx = getArrayContext(thisMPlug)

    if ctx is not None:
        outMPlug.selectAncestorLogicalIndex(*ctx)
    return outMPlug

def getComponentBundle(lookup:str) -> tuple[om.MDagPath, om.MObject]:
    """
    .. warning::
        If the lookup is ambiguous, the first match will be returned.

    :param lookup: the path to a component
    :raises Str2ApiNoMatchError: No match for the given lookup.
    :raises Str2ApiTypeError: The lookup is valid, but doesn't refer to a
        component.
    :return: A tuple of :class:`~maya.api.OpenMaya.MDagPath` and
        :class:`~maya.api.OpenMaya.MObject`.
    """
    sel = om.MSelectionList()
    try:
        sel.add(lookup)
    except RuntimeError as exc:
        _exc = str(exc)
        raise Str2ApiNoMatchError(lookup)
    try:
        return sel.getComponent(0)
    except TypeError:
        raise Str2ApiTypeError(lookup)
    except Exception as exc:
        raise Str2ApiNoMatchError(lookup)

def getAny(
        lookup:str, *,
           firstElem:bool=False,
           checkShape:bool=True
) -> tuple[
        int,
        Union[tuple[Optional[om.MDagPath], om.MObject], om.MPlug]
]:
    """
    :param lookup: a path to a node, plug or component
    :param firstElem: if it's an attribute, and it's a multi, return the
        element at logical index 0; defaults to ``False``
    :param checkShape: if *lookup* refers to an attribute on a node, and the
        node is a transform, check its shape too; defaults to ``True``
    :return: A tuple of :class:`int` (0 for node, 1 for plug, 2 for
        component) and either a tuple of (:class:`~maya.api.OpenMaya.MDagPath`
        (or None if not a DAG node) and :class:`~maya.api.OpenMaya.MObject`)
        if a node or component, or just a single
        :class:`~maya.api.OpenMaya.MPlug` if an attribute.
    """
    if '.' in lookup:
        try:
            return 1, getMPlug(lookup,
                               firstElem=firstElem, checkShape=checkShape)
        except:
            try:
                return 2, getComponentBundle(lookup)
            except Exception as exc:
                raise Str2ApiNoMatchError(
                    f"No plug or component at '{lookup}'"
                )
    return 0, getNodeBundle(lookup)