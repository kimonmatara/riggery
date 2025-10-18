from typing import Union, Optional

import maya.api.OpenMaya as om
import maya.cmds as m

from .. import api2str as _a2s
from .. import str2api as _s2a
from .parseaac import parseAddAttrCmd

from riggery.general.iterables import issublist
from riggery.general.reorder import Reorder as _Reorder

#-----------------------------------------|    Fuzzy references

def plugToRef(plug:om.MPlug) -> dict:
    """
    :return: A dictionary with these keys: 'attrNode', 'attrName',
        'logicalIndex' (the last one may be omitted).
    """
    out = {'attrNode': plug.node()}
    out['attrName'] = om.MFnAttribute(plug.attribute()).name

    if plug.isElement:
        out['logicalIndex'] = plug.logicalIndex()
    return out

def refToPlug(ref:dict) -> om.MPlug:
    """
    Reconstitutes an :class:`~maya.api.OpenMaya.MPlug` from the type of dict
    returned by :func:`plugToRef`.
    """
    out = om.MFnDependencyNode(ref['attrNode']).findPlug(ref['attrName'], False)
    try:
        return out.elementByLogicalIndex(ref['logicalIndex'])
    except KeyError:
        return out

#-----------------------------------------|    Locks

def pushUnlock(plug:om.MPlug) -> bool:
    """
    Unlocks the plug and returns a tuple of (plug, original lock state) that can
    be passed along to :func:`popUnlock`.
    """
    state = plug.isLocked
    m.setAttr(_a2s.fromMPlug(plug), l=False)
    return plug, state

def popUnlock(state:tuple[om.MPlug, bool]) -> None:
    """
    Reverses :func:`pushUnlock`.
    :param state: the type of tuple returned by :func:`pushUnlock`
    """
    m.setAttr(_a2s.fromMPlug(state[0]), l=state[1])

#-----------------------------------------|    Connections

def getInputRef(plug:om.MPlug, disconnect:bool) -> Optional[dict]:
    """
    :param disconnect: dodge locks and disconnect the input; defaults to False
    :return: A plug reference (see :func:`plugToRef`) for the input, if any.
    """
    input = plug.sourceWithConversion()
    if input.isNull:
        return None

    if disconnect:
        thisLockState = pushUnlock(plug)
        inputLockState = pushUnlock(input)

        _thisPlug = _a2s.fromMPlug(plug)
        _inputPlug = _a2s.fromMPlug(input)

        m.disconnectAttr(_inputPlug, _thisPlug)

        popUnlock(thisLockState)
        popUnlock(inputLockState)

    return plugToRef(input)

def getOutputRefs(plug:om.MPlug, disconnect:bool) -> list[dict]:
    """
    :param disconnect: dodge locks and disconnect the outputs; defaults to False
    :return: A list of plug references (see :func:`plugToRef`) for the outputs.
    """
    outputs = plug.destinationsWithConversions()
    if outputs:
        if disconnect:
            thisLockState = pushUnlock(plug)
            outputLockStates = [pushUnlock(x) for x in outputs]
        _thisPlug = _a2s.fromMPlug(plug)
        for output in outputs:
            m.disconnectAttr(_thisPlug, _a2s.fromMPlug(output))
        popUnlock(thisLockState)
        for lockState in outputLockStates:
            popUnlock(lockState)
    return list(map(plugToRef, outputs))

def getConnections(plug:om.MPlug, disconnect:bool=False) -> dict:
    """
    :param disconnect: dodge locks and disconnect inputs and outputs; defaults
        to False
    :return: A dictionary with two keys, either of which may be omitted:
        'input', 'outputs', containing the results of :func:`getInputRef` and
        :func:`getOutputRefs`, respectively.
    """
    out = {}
    input = getInputRef(plug, disconnect=disconnect)
    if input is not None:
        out['input'] = input
    outputs = getOutputRefs(plug, disconnect=disconnect)
    if outputs:
        out['outputs'] = outputs
    return out

def recreateConnections(plug:om.MPlug, connectionInfo:dict) -> None:
    """
    Recreates connections using the type of dictionary returned by
    :func:`getConnections`.
    """
    if connectionInfo:
        _plug = _a2s.fromMPlug(plug)
        thisLockState = pushUnlock(plug)

        input = connectionInfo.get('input')

        if input is not None:
            input = refToPlug(input)
            inputLockState = pushUnlock(input)
            m.connectAttr(_a2s.fromMPlug(input), _plug, force=True)
            popUnlock(inputLockState)

        for output in connectionInfo.get('outputs', []):
            output = refToPlug(output)
            outputLockState = pushUnlock(output)
            m.connectAttr(_plug, _a2s.fromMPlug(output), force=True)
            popUnlock(outputLockState)

#-----------------------------------------|    Sections

def plugIsSection(plug:om.MPlug) -> bool:
    """
    In riggery, an attribute is considered a 'section' attribute if the
    following applies:
    -   It's an enum
    -   There's only a single enum name, i.e. a single space
    -   The attribute is locked

    :return: True if *plug* is a section attribute.
    """
    if plug.isLocked:
        mobj = plug.attribute()

        if mobj.hasFn(om.MFn.kEnumAttribute):
            fn = om.MFnEnumAttribute(mobj)
            min = fn.getMin()
            max = fn.getMax()
            if min == max:
                enumName = fn.fieldName(min)
                return enumName == ' '
    return False

def createSection(node:om.MObject, name:str) -> om.MPlug:
    """
    Adds a section attribute.

    :param node: the node on which to add the attribute
    :param name: the section name; this will be conformed to uppercase
    :return: The generated plug.
    """
    _node = _a2s.fromNodeMObject(node)
    m.addAttr(_node, ln=name, at='enum', k=False, enumName=' ')
    plug = om.MFnDependencyNode(node).findPlug(name, False)
    _attrPath = _a2s.fromMPlug(plug)
    m.setAttr(_attrPath, e=True, cb=True, l=True)
    return plug

def removeSection(node:om.MObject, sectionName:str):
    """
    Removes a section attribute.
    :raises AttributeError: the specified section doesn't exist
    """
    if hasSection(node, sectionName):
        nodeFn = om.MFnDependencyNode(node)
        plug = nodeFn.findPlug(sectionName, False)
        _attr = _a2s.fromMPlug(plug)
        m.setAttr(_attr, lock=False)
        m.deleteAttr(_attr)
    else:
        raise AttributeError("section doesn't exist")

def getSectionMembers(node:om.MObject, sectionName:str) -> list[str]:
    """
    :return: The names of all attributes on *node* that belong to the specified
        section.
    """
    attrs = getReorderablePlugs(node)

    sectionIndex = list(attrs).index(sectionName)
    attrsBelow = {k: attrs[k] for k in list(attrs)[sectionIndex+1:]}

    out = []

    for k, v in attrsBelow.items():
        if plugIsSection(v):
            break
        out.append(k)

    return out

def getSectionFromMember(node:om.MObject, memberName:str) -> Optional[str]:
    """
    :param node: the node holding the attribute
    :param memberName: the name of the section member
    :return: If attribute *memberName* belongs to a section, the section name;
        otherwise, None.
    """
    attrs = getReorderablePlugs(node)
    keys = list(attrs)
    memberIndex = keys.index(memberName)
    indicesAbove = list(range(memberIndex))

    for index in reversed(indicesAbove):
        key = keys[index]
        plug = attrs[key]
        if plugIsSection(plug):
            return om.MFnAttribute(plug.attribute()).name

def hasSection(node:om.MObject, sectionName:str) -> bool:
    try:
        plug = om.MFnDependencyNode(node).findPlug(sectionName, False)
    except RuntimeError:
        return False
    return plugIsSection(plug)

def getSectionNames(node:om.MObject) -> list[str]:
    """
    :return: The names of all the attribute sections on the specified node.
    """
    out = []
    for k, v in getReorderablePlugs(node).items():
        if plugIsSection(v):
            out.append(k)
    return out

def getSectionMap(node:om.MObject) -> dict[str:list[str]]:
    """
    :return: A dictionary where each key is a section name and each value is a
        list of the names of the section's members.
    """
    return {k: getSectionMembers(node, k) for k in getSectionNames(node)}

def collectIntoSection(node:om.MObject,
                       sectionName:str,
                       memberNames:list[str],
                       atTop:bool=False) -> list[om.MPlug]:
    existingMembers = getSectionMembers(node, sectionName)
    newMembers = conformToLongNames(node, memberNames)
    _newMembers = [x for x in newMembers if x not in existingMembers]

    if _newMembers:
        if atTop:
            rebuildList = [sectionName] + _newMembers + existingMembers
        else:
            rebuildList = [sectionName] + existingMembers + _newMembers
        reorder(node, rebuildList, expandSections=True)
    return [om.MFnDependencyNode(node).findPlug(x, False) for x in newMembers]

#-----------------------------------------|    Reorder

def plugIsReorderable(plug:om.MPlug) -> bool:
    """
    :param plug: the plug to inspect
    :return: True if this plug can be reordered.
    """
    return all((plug.isDynamic,
                not plug.isArray,
                not plug.isCompound,
                not plug.isElement,
                not plug.isChild,
                plug.isKeyable or plug.isChannelBox))

def getPlugMacro(plug:om.MPlug, disconnect:bool=False) -> dict:
    """
    :param plug: the plug to inspect
    :param disconnect: if True, disconnect all inputs and outputs; defaults to
        False
    :return: A dictionary description of this plug. This is not
        JSON-serializable.
    """
    out = {}

    # Get attr ref
    out['ref'] = plugToRef(plug)

    # Get add attr dictionary
    out['addAttrKwargs'] = parseAddAttrCmd(
        om.MFnAttribute(plug.attribute()).getAddAttrCmd(True)
    )

    # Get lock state
    out['isLocked'] = plug.isLocked

    # Get cb / k
    out['isKeyable'] = plug.isKeyable
    out['isChannelBox'] = plug.isChannelBox

    # Get connection info
    connections = getConnections(plug, disconnect=disconnect)
    if connections:
        out['connections'] = connections

    return out

def deletePlug(plug:om.MPlug) -> dict:
    """
    Deletes the specified plug and returns a dictionary that can be used to
    recreate it.
    """
    wasLocked = plug.isLocked
    macro = getPlugMacro(plug, disconnect=True)
    _plug = _a2s.fromMPlug(plug)

    if wasLocked:
        m.setAttr(_plug, l=False)

    m.deleteAttr(_plug)
    return macro

def recreatePlug(macro:dict) -> om.MPlug:
    """
    Recreates a plug using the type of dictionary returned by
    :func:`deletePlug`.
    """
    node = macro['ref']['attrNode']
    _node = _a2s.fromNodeMObject(node)
    m.addAttr(_node, **macro['addAttrKwargs'])
    plug = refToPlug(macro['ref'])
    try:
        recreateConnections(plug, macro['connections'])
    except KeyError:
        pass

    _plug = _a2s.fromMPlug(plug)

    m.setAttr(_plug, keyable=False)
    m.setAttr(_plug, channelBox=False)

    if macro['isKeyable']:
        m.setAttr(_plug, keyable=True)

    elif macro['isChannelBox']:
        m.setAttr(_plug, channelBox=True)

    if macro['isLocked']:
        m.setAttr(_plug, l=True)

    return plug

def getReorderablePlugs(node:om.MObject) -> dict[str:om.MPlug]:
    """
    :return: A dictionary of ``attribute name: plug``.
    """
    nodeFn = om.MFnDependencyNode(node)
    allAttrs = [nodeFn.attribute(x) for x in range(nodeFn.attributeCount())]
    out = {}

    for attr in allAttrs:
        plug = om.MPlug(node, attr)
        if plugIsReorderable(plug):
            out[om.MFnAttribute(attr).name] = plug

    return out

#-----------------------------------------|    Reorder

def conformToLongName(node:om.MObject, attrName:str) -> str:
    """
    :param node: the node that owns the attribute
    :param attrName: the name of the attribute
    :return: The long name of the attribute.
    """
    return om.MFnAttribute(om.MFnDependencyNode(node).attribute(attrName)).name

def conformToLongNames(node:om.MObject, attrNames:list[str]) -> list[str]:
    """
    :param node: the node that owns the attributes
    :param attrName: the name of the attributes
    :return: The long names of the attributes, in a list.
    """
    nodeFn = om.MFnDependencyNode(node)
    return [om.MFnAttribute(nodeFn.attribute(x)).name for x in attrNames]

def reorder(node:om.MObject,
            attrNames:list[str],
            expandSections:bool=False,
            test=False) -> list[om.MPlug]:
    """
    Deletes and recreates the specified attributes, so that they appear in the
    requested order. Does nothing if the attributes are already in the specified
    order.

    :param node: the node that owns the attributes
    :param attrNames: the names of the attributes to rebuild, in the order they
        should be rebuilt in
    :param expandSections: if some of the names in *attrNames* refer to
        section attributes, expand them to treat their members as a bundle;
        defaults to False
    :return: The resolved plugs.
    """
    attrNames = conformToLongNames(node, attrNames)

    if expandSections:
        # If any sections are mentioned in the reorder list, remove their
        # members from anyplace else, and expand the original mention

        _attrNames = []

        sectionMap = getSectionMap(node)
        mentionedSections = set(attrNames).intersection(set(sectionMap))

        for attrName in attrNames:
            if attrName in sectionMap:
                # If this is a section, expand it and add to list
                _attrNames.append(attrName)
                _attrNames += sectionMap[attrName]
            else:
                # Not a section. If it's a member of the mentioned sections,
                # omit it; otherwise, include it

                if any((attrName in sectionMap[k] for k in mentionedSections)):
                    continue
                _attrNames.append(attrName)
        attrNames = _attrNames

    reorderableKeys = list(getReorderablePlugs(node))
    nodeFn = om.MFnDependencyNode(node)

    if issublist(attrNames, reorderableKeys):
        return [nodeFn.findPlug(x, False) for x in attrNames]

    plugsToDelete = [nodeFn.findPlug(x, False) for x in attrNames]

    macros = [deletePlug(x) for x in plugsToDelete]
    out = [recreatePlug(x) for x in macros]
    return out

def shiftMulti(node:om.MObject,
               attrsToMove:list[str],
               offset:int, *,
               expandSections:bool=False,
               roll:bool=False) -> list[om.MPlug]:
    """
    Shifts multiple attributes up or down in the Channel Box.
    """
    attrsToMove = conformToLongNames(node, attrsToMove)
    allNames = _Reorder(getReorderablePlugs(node))
    allNames.shift(attrsToMove, offset, roll)
    reorder(node, allNames, expandSections=expandSections)
    nodeFn = om.MFnDependencyNode(node)
    return [nodeFn.findPlug(x, False) for x in attrsToMove]

def sendToTop(node:om.MObject, attrsToMove:list[str],
              expandSections:bool=False,
              test=False) -> list[om.MPlug]:
    attrsToMove = conformToLongNames(node, attrsToMove)
    allNames = [x for x in getReorderablePlugs(node)
                if x not in attrsToMove]
    reorderList = attrsToMove + allNames
    reorder(node, reorderList, expandSections=expandSections,test=test)