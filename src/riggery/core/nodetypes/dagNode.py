from functools import cached_property
from typing import Generator, Optional, Union, Iterable

import maya.api.OpenMaya as om
import maya.cmds as m

from ..nodetypes import __pool__ as nodes
from ..elem import Elem, ElemInstError
from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists
from ..lib import names as _n
from riggery.internal import str2api as _s2a, \
    api2str as _a2s, \
    nodeinfo as _ni, \
    cmdinfo as _ci, \
    mfnmatches as _mfm


class DagNode(nodes['DependNode']):

    #-----------------------------------------|    Constructor(s)

    @classmethod
    @short(name='n', parent='p')
    def createNode(cls, /, name=None, parent=None):
        """
        Creates a node of this type.

        :param name/n: if omitted, uses name blocks
        :param parent/p: an optional destination parent for the node
        :return: The node.
        """
        if issubclass(cls, nodes['Shape']):
            return cls._createAsShape(name=name, parent=parent)

        nodeType = cls.__melnode__
        kwargs = {}

        name = _n.resolveNameArg(name, nodeType=nodeType)
        if name:
            kwargs['name'] = name

        if parent:
            kwargs['parent'] = _a2s.getNodeMObject(parent) \
                if isinstance(parent, str) \
                else parent.__apimobject__()

        return cls.fromMObject(
            om.MFnDagNode().create(nodeType, **kwargs)
        )

    @classmethod
    def _createAsShape(cls, *, name=None, parent=None):
        kwargs = {}

        if parent is None:
            """
            Creating without a custom parent.
            Evaluate the name fully, use it later to rename the parent
            """
            hasCustomParent = False
            name = _n.resolveNameArg(name, nodeType=cls.__melnode__)
        else:
            """
            Creating with custom parent.
            Add 'name' to kwargs only if it was passed explicitly;
            otherwise, go in later and run conform shape name
            """
            hasCustomParent = True
            parent = Elem(parent)
            kwargs['parent'] = parent.__apimobject__()
            if name:
                kwargs['name'] = name


        mFn = om.MFnDagNode()
        result = mFn.create(cls.__melnode__, **kwargs)

        if hasCustomParent:
            out = cls.fromMObject(result)
            if not name:
                out.conformShapeName()
            return out
        else:
            out = cls.fromMObject(mFn.child(0))
            if name:
                mFn.setName(name)
            out.conformShapeName()

        return out

    #-----------------------------------------|    Instance

    @classmethod
    def fromStr(cls, path:str):
        """
        :param path: the path to the node
        :raises ElemInstError: Could not instantiate from the specified path.
        :return: A :class:`~riggery.core.elem.Elem` instance for the node.
        """
        try:
            return cls.fromMDagPath(_s2a.getMDagPath(path))
        except _s2a.Str2ApiNoMatchError as exc:
            raise ElemInstError(str(exc))

    @classmethod
    def fromMObject(cls, obj:om.MObject):
        return cls.fromMDagPath(om.MFnDagNode(obj).getPath())

    @classmethod
    def fromMDagPath(cls, dagPath:om.MDagPath):
        key = _ni.getKeyFromMObject(dagPath.node())
        T = cls.__pool__[key]
        apiObjects = {'MDagPath': dagPath}
        return cls._constructInst(T, apiObjects)

    #-----------------------------------------|    API

    @property
    def _mObject(self): # unchecked
        try:
            return self.__apiobjects__.setdefault(
                'MObject',
                self.__apiobjects__['MDagPath'].node()
            )
        except RuntimeError:
            raise ElemInstError("Object removed")

    @cached_property
    def __mfntypes__(self):
        return _mfm.MFNMATCHES[self._mObject.apiType()]

    def __apimfn__(self, dag:bool=False):
        """
        :param dag: instantiate around the DAG path rather than the MObject;
            defaults to False
        :return:
        """
        return self.__mfntype__(
            self.__apimdagpath__() if dag else self.__apimobject__()
        )

    def __apimdagpath__(self) -> om.MDagPath:
        path = self.__apiobjects__['MDagPath']
        if path.isValid():
            node = path.node()
            if om.MObjectHandle(node).isValid():
                return path
        raise ElemInstError("Object removed")

    def __apimobject__(self) -> om.MObject:
        path = self.__apiobjects__['MDagPath']
        if path.isValid():
            mobj = self._mObject
            handle = om.MObjectHandle(mobj)
            if handle.isValid():
                return mobj
        raise ElemInstError("Object removed")

    def exists(self) -> bool:
        """
        :return: True if this node exists.
        """
        path = self.__apiobjects__['MDagPath']
        if path.isValid():
            node = path.node()
            return om.MObjectHandle(node).isValid()
        return False

    def removeInstance(self) -> None:
        """
        Removes this object at the instance level, preserving any other
        instances in the scene.
        """
        m.parent(str(self), removeObject=True)

    #-----------------------------------------|    Hierarchy

    def iterSiblings(self) -> Generator:
        """
        Yields other objects under this object's parent.
        """
        parent = self.parent
        if parent is None:
            for item in m.ls('|*', type='dagNode', recursive=True):
                elem = DagNode(item)
                if elem == self:
                    continue
                yield elem
        else:
            for child in parent.children:
                if child == self:
                    continue
                yield child

    siblings = property(iterSiblings)

    def getSiblings(self) -> list:
        """
        Flat version of :meth:`iterSiblings`.
        """
        return list(self.iterSiblings())

    def iterParents(self) -> Generator:
        """
        Yields this node's parents.

        Property: `.parents`
        """
        current = self.__apimdagpath__()

        while True:
            current = om.MDagPath(current)
            current.pop(1)
            node = current.node()
            if node.apiType() == 247:
                break
            yield DagNode.fromMDagPath(current)

    parents = property(iterParents)

    def getParents(self) -> list:
        """
        Flat version of :meth:`iterParents`.
        """
        return list(self.iterParents())

    def hasParent(self, node) -> bool:
        """
        :return: True if *node* is a parent of this node.
        """
        return DagNode(node) in self.parents

    def getParent(self, index=1):
        """
        Property: ``.parent``

        :param index: the index of the parent to retrieve, starting at 1 for
            the immediate parent; negative indices will traverse backwards
            from the topmost parent; defaults to 1
        :return: This node's parent, or None if the object is parented to the
            world.
        """
        if index < 0:
            return list(self.iterParents())[index]

        if index == 0:
            return self

        for i, parent in enumerate(self.iterParents(), start=1):
            if i == index:
                return parent

        if index > 1:
            raise IndexError("Index out of range.")

    parent = property(getParent)

    @_ci.useCmdFlags('listRelatives', skip=['fullPath', 'path'])
    def iterRelatives(self, **kwargs) -> Generator:
        """
        Thin generator wrapper for :func:`maya.cmds.listRelatives`.

        :param \*\*kwargs: forwarded to the Maya command
        """
        kwargs['path'] = True
        result = m.listRelatives(str(self), **kwargs)
        if result:
            for item in result:
                yield DagNode(item)

    def listRelatives(self, **kwargs) -> list:
        """
        Thin wrapper for :func:`maya.cmds.listRelatives`.

        :param \*\*kwargs: forwarded to the Maya command
        """
        return list(self.iterRelatives(**kwargs))

    def iterChildren(self, *,
                     type:Optional[Union[str, list[str]]]=None,
                     recurse:bool=False) -> Generator:
        """
        Iterates over this node's children.

        :param type: optional type filter(s); defaults to None
        :param recurse/r: return children of children too; defaults to False
        """
        kwargs = {'path':True}
        if type:
            kwargs['type'] = type
        if recurse:
            kwargs['allDescendents'] = True
        result = m.listRelatives(str(self), **kwargs)
        if result:
            for item in result:
                yield DagNode(item)

    children = property(iterChildren)

    def getChildren(self, **kwargs) -> list:
        """
        Flat version of :meth:`iterChildren`.
        """
        return list(self.iterChildren(**kwargs))

    def isIntermediate(self) -> bool:
        """
        :return: True if this is an intermediate object.
        """
        return om.MFnDagNode(self.__apimobject__()).isIntermediateObject

    def inUnderWorld(self) -> bool:
        """
        :return: True if this object is in the underworld.
        """
        return om.MFnDagNode(self.__apimobject__()).inUnderWorld

    #-----------------------------------------|    Show / hide

    def show(self, **kwargs):
        """
        Thin wrapper for :func:`maya.cmds.showHidden`.
        :return: self
        """
        m.showHidden(str(self), **kwargs)
        return self

    def hide(self, **kwargs):
        """
        Thin wrapper for :func:`maya.cmds.hide`.
        :return: self
        """
        m.hide(str(self), **kwargs)
        return self

    #-----------------------------------------|    Rigging

    def getControllerTag(self):
        """
        :return: This node's controller tag, if any.
        """
        out = m.controller(str(self), q=True)
        if out:
            return Elem(out[0])

    controllerTag = property(fget=getControllerTag)

    def getPickWalkParent(self):
        """
        If this object is a controller, returns its pick-walk parent.
        """
        out = m.controller(str(self), q=True, parent=True)
        if out:
            sfd = m.connectionInfo(f"{out}.controllerObject", sfd=True)
            if sfd:
                return nodes['DependNode'](sfd.split('.')[0])

    def setPickWalkParent(self, parent):
        """
        Tags this object as a controller and sets its pick-walk parent.
        :return: self
        """
        m.controller(str(self), str(parent), parent=True)
        return self

    def clearPickWalkParent(self):
        """
        If this object is a controller, clears its pick-walk parent.
        :return: self
        """
        _self = str(self)
        parent = m.controller(_self, q=True, parent=True)
        if parent:
            m.controller(_self, parent, e=True, unparent=True)
        return self

    pickWalkParent = property(getPickWalkParent,
                              setPickWalkParent,
                              clearPickWalkParent)

    def iterPickWalkChildren(self) -> Generator:
        """
        Yields pick-walk children for this object, if it's a controller.
        """
        out = m.controller(str(self), q=True, children=True)
        if out:
            DependNode = nodes['DependNode']
            for x in out:
                yield DependNode(x)

    def setPickWalkChildren(self, *children):
        """
        Tags this object as a controller and sets its pick-walk children.
        """
        self.clearPickWalkChildren()
        children = expand_tuples_lists(*children)
        _self = str(self)
        for child in children:
            m.controller(str(child), _self, parent=True)
        return self

    def clearPickWalkChildren(self):
        """
        If this object is a controller, clears its pick-walk children.
        """
        _self = str(self)
        for child in self.iterPickWalkChildren():
            m.controller(str(child), _self, edit=True, unparent=True)
        return self

    pickWalkChildren = property(iterPickWalkChildren,
                                setPickWalkChildren,
                                clearPickWalkChildren)

    #-----------------------------------------|    Repr

    def absoluteName(self, *, short:bool=False) -> str:
        """
        :param short: discard DAG information and just return the short name;
            defaults to False
        """
        if short:
            return om.MFnDependencyNode(self.__apimobject__()).absoluteName()
        out = []
        current = om.MFnDagNode(self.__apimobject__())
        while True:
            out.append(current.absoluteName())
            parent = current.parent(0)
            if parent.apiType() == om.MFn.kWorld:
                break
            current = om.MFnDagNode(parent)
        return '|'.join(reversed(out))

    def getName(self) -> str:
        """
        :return: This node's shortest unique DAG path.
        """
        return self.__apimdagpath__().partialPathName()