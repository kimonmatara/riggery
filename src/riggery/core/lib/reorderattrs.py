"""Tools for attribute reordering."""

from math import radians
import re
from typing import Optional, Union, Generator
from functools import cached_property

import maya.api.OpenMaya as om
import maya.cmds as m

from ..lib.nativeunits import nativeunits
import riggery.internal.api2str as _a2s
import riggery.internal.hashing as _hsh
from riggery.internal.plugutil.parseaac import parseAddAttrCmd

@nativeunits
def _addTestAttrs(node:str):
    m.addAttr(node, ln='alpha', k=True)
    m.addAttr(node, ln='beta', k=True, at='doubleAngle')
    m.addAttr(node, ln='gamma', k=True, at='doubleLinear')
    m.addAttr(node, ln='delta', k=True, at='bool')

    m.setKeyframe(f"{node}.alpha")
    m.setAttr(f"{node}.beta", radians(90), lock=True)

    m.addAttr(node, ln='epsilon', at='double3', nc=3, k=1)
    m.addAttr(node, ln='epsilonX', at='double', k=1, parent='epsilon')
    m.addAttr(node, ln='epsilonY', at='double', k=1, parent='epsilon')
    m.addAttr(node, ln='epsilonZ', at='double', k=1, parent='epsilon')

    m.setKeyframe(f"{node}.epsilon")

    m.connectAttr(f"{node}.alpha", f"{node}.gamma")

#-------------------------------------------|
#-------------------------------------------|    Errors
#-------------------------------------------|

class AttrReorderError(RuntimeError):
    ...

#-------------------------------------------|
#-------------------------------------------|    Constants
#-------------------------------------------|

SCALARTYPES = {'bool', 'long', 'short', 'byte', 'char', 'enum', 'float',
               'double', 'doubleAngle', 'doubleLinear', 'time'}

TENSORTYPES = re.compile(r"^(float|double|long|short|)[23]$")

#-------------------------------------------|
#-------------------------------------------|    Class
#-------------------------------------------|

class ReorderableAttr:

    @classmethod
    def fromNode(cls, node) -> list:
        return list(cls.iterFromNode(node))

    @classmethod
    def iterFromNode(cls, node:om.MObject) -> Generator:
        _node = _a2s.fromNodeMObject(node)
        attrs = m.listAttr(_node, ud=True)
        if attrs:
            for attr in attrs:
                try:
                    yield ReorderableAttr(node, attr)
                except AttrReorderError:
                    continue

    #---------------------------------------|    Inst

    def __init__(self, node:om.MObject, attrName:str, /, asChild:bool=False):
        self._node = node
        self._attrName = None
        self._iniAsChild = asChild
        self._children = None
        self._macro = None
        self._buildMacro(attrName)

    #---------------------------------------|    Properties

    @property
    def children(self) -> list['ReorderableAttr']:
        return self._children

    @property
    def macro(self) -> dict:
        return self._macro
    
    @property
    def node(self) -> om.MObject:
        return self._node

    @cached_property
    def nodePath(self) -> str:
        return _a2s.fromNodeMObject(self.node)

    @cached_property
    def nodeFn(self) -> om.MFnDependencyNode:
        return om.MFnDependencyNode(self.node)

    @property
    def attrName(self) -> str:
        return self._attrName

    @cached_property
    def attrPath(self) -> str:
        return '.'.join([self.nodePath, self.attrName])

    @cached_property
    def attr(self) -> om.MObject:
        return self.nodeFn.attribute(self.attrName)

    @cached_property
    def attrFn(self) -> om.MFnAttribute:
        return om.MFnAttribute(self.attr)

    @cached_property
    def plug(self) -> om.MPlug:
        return om.MPlug(self.node, self.attr)

    def invalidate(self):
        del(self.plug)
        del(self.attr)
        del(self.attrFn)

    #---------------------------------------|    Analysis

    @nativeunits
    def _buildMacro(self, userAttrName:str):
        self.attr = self.nodeFn.attribute(userAttrName)
        self.plug = om.MPlug(self.node, self.attr)
        self._attrName = self.attrFn.name

        #--------------------------|    Test eligible

        if not self.plug.isDynamic:
            raise AttrReorderError(f"Not dynamic: {self.plug.name()}")

        if (not self._iniAsChild) and self.plug.isChild:
            raise AttrReorderError(f"Compound child: {self.plug.name()}")

        if self.plug.isElement:
            raise AttrReorderError(f"Multi element: {self.plug.name()}")

        if not (self.plug.isKeyable or self.plug.isChannelBox):
            raise AttrReorderError(
                f"Not keyable or settable: {self.plug.name()}"
            )

        buildKwargs = parseAddAttrCmd(self.attrFn.getAddAttrCmd(True))

        if self.plug.isKeyable:
            buildKwargs['keyable'] = True

        attrType = buildKwargs.get('attributeType')

        if attrType is None:
            raise AttrReorderError(f"Non-reorderable: {self.plug.name()}")

        if attrType in SCALARTYPES:
            isCompound = False
        elif re.match(TENSORTYPES, attrType):
            isCompound = True
        else:
            raise AttrReorderError(f"Non-reorderable: {self.plug.name()}")

        #--------------------------|    Gather info

        macro = {'buildKwargs': buildKwargs}
        macro['lockState'] = lockState = self.plug.isLocked
        if self.plug.isChannelBox:
            macro['channelBox'] = True

        value = m.getAttr(self.attrPath)

        if isCompound:
            value = value[0]

        macro['value'] = value

        input = self.plug.sourceWithConversion()

        if not input.isNull:
            macro['inputLockState'] = input.isLocked
            macro['input'] = input = _a2s.fromMPlug(input)

        outputs = self.plug.destinationsWithConversions()

        if outputs:
            macro['outputLockStates'] = [output.isLocked \
                                         for output in outputs]
            macro['outputs'] = list(map(_a2s.fromMPlug, outputs))

        if isCompound:
            children = []
            for i in range(self.plug.numChildren()):
                child = self.plug.child(i)
                name = om.MFnAttribute(child.attribute()).name
                children.append(ReorderableAttr(self.node,
                                                name,
                                                asChild=True))
            self._children = children

        macro['attrPath'] = self.attrPath
        self._macro = macro

    #---------------------------------------|    Actions

    def _release(self):
        locked = self.macro.get('lockState', False)
        if locked:
            m.setAttr(self.attrPath, lock=False)

        children = self.children
        if children:
            for child in self.children:
                child._release()

        input = self.macro.get('input')

        if input:
            locked = self.macro.get('inputLockState', False)
            if locked:
                m.setAttr(input, lock=False)
            m.disconnectAttr(input, self.attrPath)

        for output, locked in zip(self.macro.get('outputs', []),
                                  self.macro.get('outputLockStates', [])):
            if locked:
                m.setAttr(output, lock=False)
            m.disconnectAttr(self.attrPath, output)

    def remove(self):
        self._release()
        m.deleteAttr(self.attrPath)
        self.invalidate()

        if self.children:
            for child in self.children:
                child.invalidate()

    def recreate(self):
        self._recreate()
        self._reconfigure()

    def _recreate(self):
        m.addAttr(self.nodePath, **self.macro['buildKwargs'])
        if self.macro.get('channelBox'):
            m.setAttr(self.attrPath, cb=True)

        if self.children:
            for child in self.children:
                child._recreate()

    @nativeunits
    def _reconfigure(self):
        input = self.macro.get('input')
        if input:
            m.connectAttr(input, self.attrPath)
            if self.macro['inputLockState']:
                m.setAttr(input, lock=True)
        else:
            if self.children:
                m.setAttr(self.attrPath, *self.macro['value'])
            else:
                m.setAttr(self.attrPath, self.macro['value'])

        for output, outputLockState in zip(
            self.macro.get('outputs', []),
            self.macro.get('outputLockStates', []),
        ):
            m.connectAttr(self.attrPath, output)
            if outputLockState:
                m.setAttr(output, lock=True)

        if self.macro['lockState']:
            m.setAttr(self.attrPath, lock=True)

        if self.children:
            for child in self.children:
                child._reconfigure()

    #---------------------------------------|    Repr

    def __hash__(self):
        return hash(self.attrPath)

    def __eq__(self, other):
        return isinstance(other, ReorderableAttr) \
            and hash(self) == hash(other)

    def __str__(self):
        return self.attrPath

    def __repr__(self):
        return "{}({})".format(type(self).__name__, repr(self.attrPath))

def _calcRebuildList(fullList, elemsToMove):
    """
    Calculate the full reordered list (all attrs)
    Calc deltas for every member
    Where a member's delta has increased, add that to rebuild list
    """
    if len(set(elemsToMove)) < len(elemsToMove):
        raise AttrReorderError("Duplicate elements in reorder list")

    if any((elem not in fullList for elem in elemsToMove)):
        raise AttrReorderError("Non-reorderable elements")

    firstElemIndex = fullList.index(elemsToMove[0])

    head = fullList[:firstElemIndex]
    head = [item for item in head if item not in elemsToMove]
    tail = [item for item in fullList if item not in (head+elemsToMove)]

    newList = head + elemsToMove + tail

    startIndex = None

    for i, x in enumerate(newList):
        newIndex = i
        oldIndex = fullList.index(x)
        delta = newIndex - oldIndex
        if delta < 0:
            startIndex = i+1
            break

    if startIndex is None:
        return []
    return newList[startIndex:]

def iterReorderableAttrs(
        node:om.MObject,
        plugs=False
) -> Generator[Union[ReorderableAttr, om.MPlug], None, None]:
    """
    For external use. Yields :class:`ReorderableAttr` instances for every
    reorderable attribute on *node*.

    :param plugs: yield :class:`~maya.api.OpenMaya.MPlug` instances instead;
        defaults to False
    """
    for attrName in m.listAttr(_a2s.fromNodeMObject(node), ud=True):
        try:
            out = ReorderableAttr(node, attrName)
            if plugs:
                yield out.plug
            else:
                yield out
        except AttrReorderError:
            continue

def iterReorderablePlugs(node:om.MObject) -> Generator[om.MPlug, None, None]:
    """
    Convenience function. Equivalent to :func:`iterReorderableAttrs` with
    *plugs=True*.
    """
    for x in iterReorderableAttrs(node, plugs=True):
        yield x

def reorderAttrs(node:om.MObject, attrNames:list[str]) -> list[om.MPlug]:
    """
    :param node: the node holding the attributs
    :param attrNames: the names of the attributes to reorder
    :return: :class:`~maya.api.OpenMaya.MPlug` instances for the specified
        attributes.
    """
    allAttrs = ReorderableAttr.fromNode(node)

    # The valmap is required because of a bug whereby some attribute values
    # change after the .remove() step, not sure why

    valmap = {}
    for attr in allAttrs:
        try:
            valmap[attr.attrPath] = m.getAttr(attr.attrPath)
        except:
            continue

    requestedAttrs = [ReorderableAttr(node, x) for x in attrNames]
    workStack = _calcRebuildList(allAttrs, requestedAttrs)

    if workStack:
        for attr in workStack:
            attr.remove()

        for attr in workStack:
            attr.recreate()

    for attrPath, val in valmap.items():
        try:
            m.setAttr(attrPath, val)
        except:
            continue

    return [inst.plug for inst in requestedAttrs]