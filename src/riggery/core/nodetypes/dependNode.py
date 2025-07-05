from functools import cached_property
import re
from typing import Union, Optional, Generator, Iterable, Literal
import os

import maya.cmds as m
import maya.api.OpenMaya as om

import riggery
from riggery.internal import cmdinfo as _ci, \
    nodeinfo as _ni, \
    hashing as _hsh, \
    mfnmatches as _mfm
import riggery.internal.str2api as _s2a
import riggery.internal.api2str as _a2s
from ..lib import reorderattrs as _roa
from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists
from ..lib import names as _n, \
    namespaces as _ns, \
    tags as _tags, \
    reorderattrs as _ra
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
from ..elem import Elem, ElemInstError


uncap = lambda x: x[0].lower()+x[1:]


class Section:
    def __init__(self, node, name:str):
        self._node = node
        self._name = name

    def node(self):
        """
        :return: The node this section belongs to.
        """
        return self._node

    def attr(self):
        """
        :return: The section's label attribute.
        """
        return self.node().attr(self.name)

    def getName(self) -> str:
        """
        Property: ``.name``

        :return: The section's name.
        """
        return self._name

    def setName(self, name):
        """
        Sets the section's name.

        Property: ``.name``
        """
        attr = self.attr()
        attr.unlock()
        m.renameAttr(str(attr), name)
        attr.lock()

    name = property(getName, setName)

    #----------------------------------|    Get members

    def __iter__(self):
        return self.node().iterSectionMembers(self.name)

    def __len__(self):
        return len(list(self.node().iterSectionMembers(self.name)))

    #----------------------------------|    Add members

    def collect(self, *names):
        """
        :param \*names: the names of the attributes to collect, packed or unpacked
        :return: The collected attributes.
        """
        return self.node().collectIntoSection(
            expand_tuples_lists(*names),
            self.name
        )

    #----------------------------------|    Remove

    def exists(self) -> bool:
        """
        :return: True if this section exists.
        """
        return self.name in self.node().iterSectionNames()

    def remove(self, includeMembers:bool=False) -> None:
        """
        :param includeMembers: remove the member attributes too; defaults to
            False
        :return: None
        """
        try:
            sectionAttr = self.node().attr(self.name)
        except AttributeError:
            return

        if includeMembers:
            for attr in self:
                attr.unlock()
                m.deleteAttr(str(attr))

        sectionAttr.unlock()
        m.deleteAttr(str(sectionAttr))

    #----------------------------------|    Repr

    def __repr__(self):
        return "{}.sections[{}]".format(
            repr(self.node()),
            repr(self.name)
        )


class Sections:
    def __init__(self, node):
        self._node = node

    def node(self):
        return self._node

    def __repr__(self):
        return "{}.sections".format(repr(self.node()))

    def names(self) -> Generator[str, None, None]:
        """
        Yields section names.
        """
        return self.node().iterSectionNames()

    #----------------------------------|    Get sections

    def __getitem__(self, item):
        node = self.node()
        if item in self.names():
            return Section(node, item)
        raise KeyError(item)

    def __iter__(self):
        node = self.node()
        for name in self.names():
            yield Section(node, name)

    def __len__(self):
        return len(list(self.node().iterSectionNames()))

    #----------------------------------|    Remove sections

    def __delitem__(self, key):
        try:
            inst = self[key]
        except KeyError:
            return
        inst.remove()

    #----------------------------------|    Add sections

    def add(self, sectionName:str) -> Section:
        """
        Adds (or retrieves) and returns a section with the specified name.
        :param sectionName: the name of the section
        """
        node = self.node()
        node.addSectionAttr(sectionName)
        return Section(node, sectionName)

class SectionsGetter:
    def __get__(self, inst, instype):
        if inst is None:
            return self
        obj = Sections(inst)
        setattr(inst, 'sections', obj)
        return obj


class DependNodeMeta(type(Elem)):

    def __new__(meta, clsname, bases, dct):
        nodeType = _ni.UNCAPMAP.get(clsname, uncap(clsname))
        dct.setdefault('__melnode__', nodeType)

        try:
            dct.setdefault('__typesuffix__', _n.TYPESUFFIXES[nodeType])
        except KeyError:
            pass

        return super().__new__(meta, clsname, bases, dct)


class DependNode(Elem, metaclass=DependNodeMeta):

    __pool__ = nodes
    __typesuffix__ = None

    sections = SectionsGetter()
    tags = _tags.TagsGetter()

    #-----------------------------------------|    Constructor(s)

    @classmethod
    def ls(cls, *patterns):
        """
        Generator. Yields objects of this type in the scene.
        """
        result = m.ls(*patterns, type=cls.__melnode__)

        if result:
            for x in result:
                x = DependNode(x)
                if isinstance(x, cls):
                    yield x

    @classmethod
    @short(name='n')
    def createNode(cls, name:Optional[str]=None):
        """
        Creates a simple instance of this node.

        Note that this *should* be overriden under
        :class:`~zulu.core.nodetypes.Shape`, otherwise naming will be mangled,
        and the wrong node type will be returned, owing to
        :meth:`~maya.api.OpenMaya.MFnDependencyNode.create` works.

        :param name/n: if omitted, name blocks will be used
        :return: The node.
        """
        nodeType = cls.__melnode__
        name = _n.resolveNameArg(name, nodeType=nodeType)
        kwargs = {}
        if name is not None:
            kwargs['name'] = name

        mFn = om.MFnDependencyNode()
        return cls.fromMObject(mFn.create(nodeType, **kwargs))

    #-----------------------------------------|    Instantiation

    @classmethod
    def fromStr(cls, path:str):
        """
        :param path: the path to the node
        :raises ElemInstError: Could not instantiate from the specified path.
        :return: A :class:`~riggery.core.elem.Elem` instance for the node.
        """
        dagPath, mObject = _s2a.getNodeBundle(path)

        T = cls.__pool__[_ni.getKeyFromMObject(mObject)]
        apiObjects = {}
        if dagPath is None:
            apiObjects['MObject'] = mObject
        else:
            apiObjects['MDagPath'] = dagPath
        return cls._constructInst(T, apiObjects)

    @classmethod
    def fromMObject(cls, obj: om.MObject):
        T = cls.__pool__[_ni.getKeyFromMObject(obj)]
        apiObjects = {}
        if obj.hasFn(om.MFn.kDagNode):
            apiObjects['MDagPath'] = om.MFnDagNode(obj).getPath()
        else:
            apiObjects['MObject'] = obj
        return cls._constructInst(T, apiObjects)

    def referTo(self, other):
        """
        Swaps out the class reference and API objects of this instance to
        match those of *other*.
        """
        other = Elem(other)
        self.__class__ = other.__class__
        self.__apiobjects__ = other.__apiobjects__

    #-----------------------------------------|    Attributes

    @short(lock='l', input='i', defaultValue='dv')
    def createAttr(self,
                   *args,
                   lock:bool=False,
                   input=None,
                   defaultValue=None,
                   **kwargs):
        """
        Wraps :meth:`addAttr` to ensure that *defaultValue/dv* is always
        interpreted in native units.
        """
        attr = self.addAttr(*args, input=input, **kwargs)
        if attr is not None:
            if defaultValue is not None:
                attr.setDefaultValue(defaultValue)
                if input is None:
                    attr.setValue(defaultValue)
            if lock:
                attr.lock()
            return attr

    @short(reuse='re',
           channelBox='cb',
           lock='l',
           input='i',
           section='s')
    @_ci.useCmdFlags('addAttr', skip='longName')
    def addAttr(self,
                attrName:str, /,
                reuse:bool=False,
                channelBox:Optional[bool]=None,
                lock:bool=False,
                input=None,
                section:Optional[str]=None,
                **kwargs):
        """
        Thin wrapper around :func:`maya.cmds.addAttr`.

        :param attrName: the long name of the attribute to add, or the name
            of the attribute to query (the *longName/ln* flag is not used)
        :param channelBox/cb: 'create' mode only; sets the channelBox state;
            defaults to None
        :param reuse/re: if an attribute already exists with the given name,
            return it; defaults to False
        :param input/i: if an attribute instance can be retrieved, connect it
            to this input (or value) before returning; defaults to False
        :param lock/l: if an attribute instance can be retrieved, lock it
            before returning; defaults to False
        :param section/s: the name of the section under which to collect this
            attribute; if the section doesn't exist, it will be created
        :param \*\*kwargs: call ``help()`` for an accurate signature
        :return: In query mode, returns the result of the query; in create
            mode, attempts to return an instance of the new attribute (may
            not be possible for compounds); otherwise, None.
        """
        editMode = kwargs.get('e', False)
        queryMode = kwargs.get('q', False)
        createMode = not(editMode or queryMode)

        args = []

        if createMode:
            if reuse:
                try:
                    return self.attr(attrName)
                except AttributeError:
                    pass
            args.append(str(self))
            kwargs['longName'] = attrName
        else:
            args.append(f"{self}.{attrName}")

        result = m.addAttr(*args, **kwargs)

        if queryMode:
            return result

        if createMode:
            try:
                out = self.attr(attrName)
            except AttributeError:
                return

            if input is not None:
                input >> out

            flags = {}

            if channelBox is not None:
                flags['channelBox'] = channelBox

            if lock:
                flags['lock'] = lock

            out.setFlags(**flags)

            if section:
                section = self.sections.add(section)
                out = section.collect(out.attrName())[0]

            return out

    @short(suffixes='suf',
           keyable='k',
           channelBox='cb',
           input='i',
           defaultValue='dv',
           asAngle='aa',
           asDistance='ad',
           lock='l',
           section='s')
    def addTripleAttr(
            self,
            basename:str, *,
            suffixes:Union[str, Iterable[str]]='XYZ',
            keyable:bool=False,
            channelBox:bool=False,
            input=None,
            defaultValue=None,
            asAngle:bool=False,
            asDistance:bool=False,
            section:Optional[str]=None,
            lock:bool=False,
            multi=False
    ):
        """
        Creates a triple compound that mimics the standard ``translate`` /
        ``rotate`` / ``scale`` attributes on transform nodes.

        :param name: a name for the new attribute
        :param keyable/k: make the attribute keyable; defaults to ``False``
        :param channelBox: make the attribute settable; defaults to ``False``
        :param input/i: an optional input; defaults to ``None``
        :param defaultValue/dv: an optional default value; defaults to ``None``
        :param lock/l: lock the attribute after creation; defaults to ``False``
        :param asAngle: use ``doubleAngle`` for the child types; defaults to
            ``False``
        :param section/s: the name of the section under which to collect this
            attribute; if the section doesn't exist, it will be created
        :param asDistance: use ``doubleLinear`` for the child types; defaults
            to ``False``
        :return: The compound attribute.
        """
        _self = str(self)

        kwargs = {}
        if multi:
            kwargs['multi'] = True

        m.addAttr(_self, ln=basename, at='double3', nc=3, **kwargs)
        childType = 'doubleLinear' if asDistance \
            else 'doubleAngle' if asAngle \
            else 'double'

        for suffix in suffixes:
            m.addAttr(_self,
                      ln=f"{basename}{suffix}",
                      at=childType,
                      parent=basename)

        root = self.attr(basename)
        if multi:
            attr = root[0]
        else:
            attr = root

        children = attr.getChildren()

        if keyable:
            attr.setFlags(keyable=True, recurse=True)

        elif channelBox:
            attr.setFlags(channelBox=True, recurse=True)

        if defaultValue is not None:
            for value, child in zip(defaultValue, children):
                m.addAttr(str(child), e=True, dv=value)
                child.set(value)

        if section:
            attr = self.sections.add(section).collect(basename)[0]

        if input is not None:
            input >> attr

        if lock:
            attr.lock(recurse=True)

        return root

    @short(asAngle='aa', asDistance='ad')
    def addPointAttr(self, *args, **kwargs):
        """
        Equivalent to :meth:`addTripleAttr` with ``asDistance=True``.
        """
        kwargs['asDistance'] = True
        kwargs['asAngle'] = False
        return self.addTripleAttr(*args, **kwargs)

    @short(channelBox='cb',
           section='s')
    def addAxisAttr(self,
                    name:str,
                    defaultAxis:Literal['x', 'y', 'z',
                                       '-x', '-y', '-z'],
                    channelBox:bool=True,
                    section:Optional[str]=None):
        """
        Adds an axis-selector attribute. The attribute will be settable
        (channel-box) by default.

        :param name: the name of the attribute
        :param defaultAxis: required; one of 'x', 'y', 'z', '-x', '-y' or '-z'
        :param channelBox/cb: make the attribute settable; defaults to
            ``True``
        :return: The attribute.
        """
        kwargs = {}
        if channelBox:
            kwargs['channelBox'] = channelBox

        return self.addAttr(
            name,
            at='enum',
            enumName=':'.join(['x', 'y', 'z', '-x', '-y', '-z']),
            dv=['x', 'y', 'z', '-x', '-y', '-z'].index(defaultAxis),
            section=section,
            **kwargs
        )

    @short(asAngle='aa', asDistance='ad')
    def addVectorAttr(self, *args, **kwargs):
        """
        Equivalent to :meth:`addTripleAttr` with ``asDistance=False`` and
        ``asAngle=False``.
        """
        kwargs['asDistance'] = kwargs['asAngle'] = False
        return self.addTripleAttr(*args, **kwargs)

    @short(channelBox='cb', keyable='k',
           defaultValue='dv', section='s')
    def addRotateOrderAttr(self,
                           name:str,
                           channelBox=None,
                           keyable=None,
                           defaultValue=None,
                           section:Optional[str]=None):
        """
        :param name: the attribute name
        :param channelBox: make it settable (by omission)
        :param keyable: make it keyable (by omission)
        :param defaultValue: a default value, in index or lowercase name form
        :param section: an optional section under which to collect
        """
        kwargs = {'at': 'enum',
                  'enumName': ':'.join(['xyz', 'yzx', 'zxy',
                                        'xzy', 'yxz', 'zyx'])}
        if section:
            kwargs['section'] = section
        if channelBox is not None:
            kwargs['channelBox'] = channelBox

        if keyable is not None:
            kwargs['keyable'] = keyable

        if defaultValue is not None:
            if isinstance(defaultValue, str):
                defaultValue = ['xyz', 'yzx', 'zxy',
                                'xzy', 'yxz', 'zyx'].index(defaultValue)
            kwargs['defaultValue'] = defaultValue

        return self.addAttr(name, **kwargs)

    @short(asAngle='aa', asDistance='ad')
    def addEulerRotationAttr(self, *args, **kwargs):
        """
        Equivalent to :meth:`addTripleAttr` with ``asAngle=True``.
        """
        kwargs['asDistance'] = False
        kwargs['asAngle'] = True
        return self.addTripleAttr(*args, **kwargs)

    @short(channelBox='cb',
           defaultValue='dv',
           section='s')
    def addColorIndexAttr(self,
                          name:str, /,
                          defaultValue=None,
                          channelBox=True,
                          section:Optional[str]=None):
        """
        Adds a simple color index attribute. Good for picking control colors
        etc.
        """
        kwargs = {'longName': name, 'minValue': 0,
                  'maxValue': 31, 'attributeType': 'short'}

        if defaultValue is not None:
            kwargs['defaultValue'] = defaultValue

        s = str(self)
        m.addAttr(s, **kwargs)

        if channelBox:
            m.setAttr(f"{s}.{name}", cb=True)

        out = self.attr(name)

        if section:
            out = self.sections.add(section).collect(name)[0]

        return out

    @short(keyable='k',
           channelBox='cb',
           defaultValue='dv',
           input='i',
           lock='l')
    def addQuatAttr(self,
                    name:str, /,
                    keyable=None,
                    channelBox=None,
                    defaultValue=None,
                    multi=False,
                    input=None,
                    lock=False):
        """
        Creates a quaternion attribute, with default values
        (0.0, 0.0, 0.0, 1.0).
        """
        _self = str(self)

        kwargs = {}
        if multi:
            kwargs['multi'] = True

        m.addAttr(_self, ln=name, at='compound', nc=4, **kwargs)

        if defaultValue is None:
            defaultValues = (0.0, 0.0, 0.0, 1.0)
        else:
            defaultValues = list(defaultValues)

        kwargs = {}

        if keyable is not None:
            kwargs['keyable'] = keyable

        if channelBox is not None:
            kwargs['channelBox'] = channelBox

        for ax, defaultValue in zip('XYZW', defaultValues):
            m.addAttr(_self,
                      ln=f"{name}{ax}",
                      at='double',
                      parent=name,
                      dv=defaultValue,
                      **kwargs)

        attr = self.attr(name)
        if input is not None:
            input >> attr
        if lock:
            attr.lock(r=True)

        return attr


    def setAttrs(self, **kwargs):
        """
        Convenience method. Sets multiple attributes at once via keyword
        arguments.
        """
        for k, v in kwargs.items():
            self.attr(k).set(v)
        return self

    def attr(self, attrName:str, *, checkShape:bool=False):
        """
        For parity with PyMEL, this does *not* auto-expand to element 0 on
        'multi' roots.

        :param attrName: the short or long name of the attribute
        :param checkShape: does nothing on :class:`DependNode`, here for
            calling parity
        """
        try:
            plug = _s2a.getMPlugOnNode(self.__apimobject__(),
                                       attrName,
                                       firstElem=False,
                                       checkShape=False)
        except _s2a.Str2ApiNoMatchError:
            raise AttributeError(attrName)
        return plugs['Attribute'].fromMPlug(plug)

    def hasAttr(self, attrName:str, checkShape:bool=True) -> bool:
        """
        Checks if this node has the specified attribute.
        :param attrName: the attribute to look for
        :param checkShape: this is here for parity with ``Transform``,
            and is ignored on ``DependNode``
        """
        return om.MFnDependencyNode(self.__apimobject__()
                                    ).hasAttribute(attrName)

    def __getattr__(self, item):
        return self.attr(item)

    @_ci.useCmdFlags('listAttr',
                     skip=['fullNodeName',
                           'leaf',
                           'nodeName',
                           'shortNames'])
    def iterAttr(self, **kwargs) -> Generator:
        """
        Iterating wrapper for :func:`~maya.cmds.listAttr`.
        """
        result = m.listAttr(str(self), **kwargs)
        if result:
            for item in result:
                yield self.attr(item)

    def iterReorderableAttrNames(self) -> Generator[str, None, None]:
        """
        Yields the local names of reorderable attributes on this node.
        """
        for inst in _roa.iterReorderableAttrs(self.__apimobject__()):
            yield inst.attrName

    def getReorderableAttrNames(self) -> Generator[str, None, None]:
        """
        Flat version of :meth:`iterReorderableAttrNames`.
        """
        return list(self.iterReorderableAttrNames())

    def listAttr(self, **kwargs):
        """
        Thin wrapper for :func:`~maya.cmds.listAttr`.
        """
        return list(self.iterAttr(**kwargs))

    def deleteAttr(self, attrName:str):
        """
        Deletes the specified dynamic attribute from this node.
        """
        m.deleteAttr(f"{self}.{attrName}")
        return self

    def reorderAttrs(self, attrNames:list[str]) -> list['Attribute']:
        """
        This only works with dynamic, scalar attributes that are visible in
        the Channel Box.

        :param attrNames: the names of the attributes to reorder
        :return: :class:`~riggery.core.plugtypes.attribute.Attribute` instances
            for all reordered attributes.
        """
        conform = plugs['Attribute'].fromMPlug
        result = _roa.reorderAttrs(self.__apimobject__(), attrNames)
        return [conform(x) for x in result]

    @short(keyable='k', channelBox='cb')
    def maskAnimAttrs(self, keyable=None, channelBox=None):
        """
        Hides all attributes except whatever's specified in *keyable* and / or
        *channelBox*.

        :param keyable/k: the names of attributes to make keyable
        :param channelBox/cb: the names of attribute make settable
        :return: self
        """
        if keyable:
            keyable = expand_tuples_lists(keyable)
        else:
            keyable = []

        if channelBox:
            channelBox = expand_tuples_lists(channelBox)
        else:
            channelBox = []

        # Disable attributes
        mobj = self.__apimobject__()

        if mobj.hasFn(om.MFn.kDagNode):
            v = self.attr('v')
            v.hide()
            v.lock()

            if mobj.hasFn(om.MFn.kTransform):
                for name in ['t','r', 's', 'ro']:
                    attr = self.attr(name)
                    attr.hide(recurse=True)
                    attr.lock(recurse=True)

        for attr in filter(
            lambda x: x.isAnimatableDynamic() and not x.isProxy(),
            self.iterAttr(userDefined=True)
        ):
            attr.hide(recurse=True)

        # Selectively enable requested attributes
        for name in keyable:
            attr = self.attr(name)
            attr.show(recurse=True, force=True)
            attr.unlock(recurse=True, force=True)

        for name in channelBox:
            attr = self.attr(name)
            attr.show(recurse=True, force=True, keyable=False)
            attr.unlock(recurse=True, force=True)

        return self

    @classmethod
    def _mPlugIsSectionAttr(cls, plug:om.MPlug) -> bool:
        mobj = plug.attribute()
        if mobj.hasFn(om.MFn.kEnumAttribute):
            fn = om.MFnEnumAttribute(mobj)
            min = fn.getMin()
            max = fn.getMax()
            return min == max \
                and fn.fieldName(min) == ' ' \
                and plug.isLocked
        return False

    def iterSectionAttrs(self) -> Generator:
        """
        Yields 'section' heading attributes.
        """
        for attr in self.iterAttr(ud=True, attributeType='enum'):
            if attr.isSectionAttr():
                yield attr

    def addSectionAttr(self, sectionName:str):
        """
        Adds a 'section' heading attribute, if it doesn't already exist.
        """
        if sectionName in self.iterSectionNames():
            return self.attr(sectionName)

        return self.addAttr(sectionName,
                            at='enum',
                            enumName=' ',
                            k=False, cb=True).lock()

    def iterSectionNames(self) -> Generator:
        """
        Yields section names.
        """
        for sectionAttr in self.iterSectionAttrs():
            yield sectionAttr.attrName()

    def sectionExists(self, sectionName:str) -> bool:
        """
        :return: True if the named section exists.
        """
        return sectionName in self.iterSectionNames()

    def iterSectionMembers(self, sectionName:str) -> Generator:
        """
        Yields members of the named section.
        """
        thing = _roa.iterReorderablePlugs(self.__apimobject__())
        started = False

        for plug in _roa.iterReorderablePlugs(
                self.__apimobject__()
        ):
            if started:
                if self._mPlugIsSectionAttr(plug):
                    break
                yield plugs['Attribute'].fromMPlug(plug)
            else:
                if self._mPlugIsSectionAttr(plug):
                    n = plug.name().split('.', 1)[1]
                    if n == sectionName:
                        started = True

    def sendSectionAbove(self, sectionName:str, attrName:str):
        sectionBundle = [sectionName] + [attr.attrName() for attr \
                            in self.iterSectionMembers(sectionName)]
        reorderStack = sectionBundle + [attrName]
        self.reorderAttrs(reorderStack)

    def iterSectionGroups(self) -> Generator[tuple[str, tuple], None, None]:
        """
        Yields pairs of *sectionName*, tuple of section member attrs
        """
        currentSection = None
        currentSectionMembers = []

        for plug in _roa.iterReorderablePlugs(self.__apimobject__()):
            if self._mPlugIsSectionAttr(plug):
                if currentSection:
                    yield currentSection, tuple(currentSectionMembers)
                currentSection = plug.name().split('.', 1)[1]
                currentSectionMembers = []
            else:
                if currentSection:
                    currentSectionMembers.append(
                        plugs['Attribute'].fromMPlug(plug)
                    )
        if currentSection:
            yield currentSection, tuple(currentSectionMembers)

    def collectIntoSection(self, attrNames:list[str], sectionName) -> list:
        """
        :param attrNames: the names of the attributes to move
        :param sectionName: the name of the section
        :param top: insert the attributes to the top of the section rather
            than append to the bottom; defaults to False
        :return: The moved attributes, in a list.
        """
        origRequest = list(attrNames)
        node = self.__apimobject__()
        existingMemberNames = [member.attrName() for member \
                               in self.iterSectionMembers(sectionName)]
        attrNames = [_roa.ReorderableAttr(node, name).attrName \
                     for name in attrNames]
        attrNames = [x for x in attrNames if x not in existingMemberNames]

        if attrNames:
            _roa.reorderAttrs(node,
                              [sectionName] + existingMemberNames + attrNames)
        return [self.attr(name) for name in origRequest]

    def sendSectionAbove(self, sectionName:str, anchorAttrName:str):
        """
        :param sectionName: the name of the section to move
        :param anchorAttrName: the name of the attribute relative to which the
            section must be moved
        """
        node = self.__apimobject__()
        anchorAttrName = _roa.ReorderableAttr(node, anchorAttrName).attrName
        memberNames = [member.longName() for member \
                       in self.iterSectionMembers(sectionName)]
        if anchorAttrName in memberNames:
            memberNames.remove(anchorAttrName)
            chunk = [sectionName] + memberNames
            _roa.reorderAttrs(node, chunk+[anchorAttrName])
        else:
            allNames = self.getReorderableAttrNames()
            anchorIndex = allNames.index(anchorAttrName)

            head = allNames[:anchorIndex]
            mid = [sectionName] + memberNames
            mid.append(anchorAttrName)
            tail = [name for name in allNames if name not in head+mid]
            _roa.reorderAttrs(node, mid+tail)

    def sendSectionBelow(self, sectionName:str, anchorAttrName:str):
        """
        :param sectionName: the name of the section to move
        :param anchorAttrName: the name of the attribute relative to which the
            section must be moved
        """
        node = self.__apimobject__()
        anchorAttrName = _roa.ReorderableAttr(node, anchorAttrName).attrName

        memberNames = [member.longName() for member \
                       in self.iterSectionMembers(sectionName)]

        if anchorAttrName in memberNames:
            memberNames.remove(anchorAttrName)
            chunk = [sectionName] + memberNames
            _roa.reorderAttrs(node, [anchorAttrName] + chunk)
        else:
            allNames = self.getReorderableAttrNames()
            anchorIndex = allNames.index(anchorAttrName)
            head = allNames[:anchorIndex+1]
            mid = [sectionName] + memberNames
            tail = [name for name in allNames if name not in head+mid]
            _roa.reorderAttrs(node, mid+tail)

    #-----------------------------------------|    API

    def __apihandle__(self) -> om.MObjectHandle:
        return self.__apiobjects__.setdefault(
            'MObjectHandle',
            om.MObjectHandle(self.__apiobjects__['MObject'])
        )

    def __apimobject__(self) -> om.MObject:
        hnd = self.__apihandle__()
        if hnd.isValid():
            return hnd.object()
        raise ElemInstError("Object removed")

    @cached_property
    def __mfntypes__(self):
        return _mfm.MFNMATCHES[self.__apiobjects__['MObject'].apiType()]

    @cached_property
    def __mfntype__(self):
        matches = self.__mfntypes__
        if len(matches) > 1:
            # If you're here, the method should be overriden for this type to
            # disambiguate the default MFn match
            raise TypeError("Too many MFn matches")
        return matches[0]

    def __apimfn__(self):
        return _mfm.fallbackInst(self.__apimobject__(), self.__mfntype__)

    #-----------------------------------------|    Authoring

    @classmethod
    def _getStubFilePath(cls) -> str:
        pdir = os.path.join(
            os.path.dirname(riggery.__file__),
            'core', cls.__pool__.__pool_package__.split('.')[-1]
        )

        filename = f"{cls.__melnode__}.py"
        return os.path.join(pdir, filename)

    @classmethod
    def _createStubContent(cls):
        clsname = cls.__name__
        pname = cls.mro()[1].__name__
        lines = [
            'from ..nodetypes import __pool__ as nodes', '', '', ''
            f"class {clsname}(nodes['{pname}']):", '',
            '    ...'
        ]
        return '\n'.join(lines)

    #-----------------------------------------|    Duplication

    @short(name='n')
    def duplicate(self, name=None):
        if name is None:
            if _n.Name.__elems__:
                name = _n.Name.evaluate(self.__typesuffix__)

        kwargs = {}
        if name:
            kwargs['name'] = name

        return list(map(Elem, m.duplicate(str(self), **kwargs)))

    #-----------------------------------------|    Selection

    def select(self, *, add=False):
        """
        Selects this node.

        :param add: add to the current selection; defaults to False
        :return: self
        """
        kwargs = {}
        if add:
            kwargs['add'] = True
        m.select(str(self), **kwargs)
        return self

    def deselect(self):
        """
        Deselects this node.

        :return: self
        """
        m.select(str(self), d=True)
        return self

    #-----------------------------------------|    Locking

    def isLocked(self) -> bool:
        """
        :return: True if the node is locked.
        """
        return om.MFnDependencyNode(
            self.__apimobject__()).isLocked

    def lock(self):
        """
        Locks this node.

        :return: self
        """
        om.MFnDependencyNode(self.__apimobject__()).isLocked = True

    def unlock(self):
        """
        Unlocks this node.

        :return: self
        """
        om.MFnDependencyNode(self.__apimobject__()).isLocked = False

    def setLocked(self, state:bool):
        """
        Sets this node's lock state.
        """
        om.MFnDependencyNode(self.__apimobject__()).isLocked = state

    locked = property(isLocked, setLocked, unlock)

    #-----------------------------------------|    Referencing

    def isReferenced(self) -> bool:
        """
        :return: True if the node is referenced.
        """
        return om.MFnDependencyNode(
            self.__apimobject__()).isFromReferencedFile

    #-----------------------------------------|    Type inspections

    def isTransform(self) -> bool:
        """
        :return: True if this is a transform node.
        """
        return False

    def isShape(self) -> bool:
        """
        :return: True if this is a shape node.
        """
        return False

    @short(inherited='i', classNames='cn')
    def virtualType(self,
                    inherited:bool=False,
                    classNames:bool=False) -> Union[str, list[str]]:
        """
        Similar to :func:`~maya.cmds.nodeType`, except returns riggery types.

        :param inherited/i: return a reverse MRO; defaults to False
        :param classNames/cn: return class names rather than lowercase type
             names; defaults to False
        """
        path = _ni.getPathFromKey(self.__class__.__name__)
        if not inherited:
            out = path[-1]
            if not classNames:
                out = _ni.UNCAPMAP.get(out, out)
            return out

        if not classNames:
            path = [_ni.UNCAPMAP.get(x, uncap(x)) for x in path]
        return path

    def nodeType(self, **kwargs) -> Union[str, list[str]]:
        """
        Thin wrapper for :func:`maya.cmds.nodeType`.

        :param \*\*kwargs: forwarded to the Maya command
        """
        if kwargs:
            return m.nodeType(str(self), **kwargs)
        return om.MFnDependencyNode(self.__apimobject__()).typeName

    #-----------------------------------------|    Rigging

    def _getControlTag(self) -> Optional[str]:
        out = m.controller(str(self), q=True, group=True)
        if out:
            return out[0]

    def _getIsControl(self):
        return bool(m.controller(str(self), q=True, isController=True))

    def _setIsControl(self, state):
        if state:
            m.controller(str(self))
        else:
            tag = self._getControlTag()
            if tag:
                m.delete(tag)

    isControl = property(_getIsControl, _setIsControl)

    #-----------------------------------------|    History

    def deleteHistory(self):
        """
        Deletes construction history on this node.
        """
        m.delete(str(self), constructionHistory=True)
        return self

    def evaluate(self):
        """
        :return: Forces graph evaluation of this node.
        """
        m.dgeval(str(self))
        return self

    #-----------------------------------------|    Repr

    def hasUniqueName(self) -> bool:
        """
        :return: True if this node's name is unique.
        """
        return om.MFnDependencyNode(self.__apimobject__()).hasUniqueName()

    def absoluteName(self) -> str:
        """
        :return: The shortest unambiguous absolute name for this node.
        """
        return om.MFnDependencyNode(self.__apimobject__()).absoluteName()

    @short(stripNamespace='sns',
           stripTypeSuffix='sts')
    def shortName(self, *,
                  stripNamespace:bool=False,
                  stripTypeSuffix:bool=False) -> str:
        """
        Returns short forms of this node's name.

        :param stripNamespace/sns: strip the namespace; defaults to False
        :param stripTypeSuffix/sts: strip the type suffix; note that this
            may result in an empty string, if the node's entire name looks
            like a type suffix; defaults to False
        :return: The shortened name.
        """
        name = self._getDepNodeName()
        if stripNamespace:
            name = name.split(':')[-1]
        if stripTypeSuffix:
            elems = name.split('_')
            if _n.looksLikeTypeSuffix(elems[-1]):
                del(elems[-1])
            name = '_'.join(elems)
        return name

    def getNamespace(self) -> str:
        """
        :return: The namespace containing this node, in absolute form.
        """
        return _ns.Namespace(
            om.MFnDependencyNode(self.__apimobject__()).namespace
        )

    def setNamespace(self, namespace):
        """
        Assigns this node to the given namespace. If the namespace doesn't
        exist, it is created.

        :param namespace: the namespace
        :return: self
        """
        ns = _ns.Namespace(namespace).actualize()
        ns.addNodes(self)
        return self

    def clearNamespace(self):
        """
        Removes this node from any namespaces.

        :return: self
        """
        _ns.Namespace(':').addNodes(self)
        return self

    namespace = property(getNamespace, setNamespace, clearNamespace)

    def _getDepNodeName(self) -> str:
        return om.MFnDependencyNode(self.__apimobject__()).name()

    def getName(self, *, absolute:bool=False):
        """
        :return: The shortest unique name for this node.
        """
        return self._getDepNodeName()

    def setName(self, name:str):
        """
        Property: ``.name``

        :param name: the name to use; prefix with ':' to perform absolute
            naming
        :return: self
        """
        m.rename(str(self), name)
        return self

    def clearName(self):
        """
        Property: ``.name``

        Renames this node according to block naming rules.
        """
        name = _n.resolveNameArg(None, typeSuffix=self.defaultTypeSuffix)
        self.setName(name if name else self.__melnode__+'1')
        return self

    def _getName(self, *args, **kwargs):
        return self.getName(*args, **kwargs)

    def _setName(self, *args, **kwargs):
        return self.setName(*args, **kwargs)

    def _clearName(self, *args, **kwargs):
        return self.clearName(*args, **kwargs)

    name = property(_getName, _setName, _clearName)

    @property
    def defaultTypeSuffix(self) -> Optional[str]:
        return self.__typesuffix__

    def exists(self) -> bool:
        """
        :return: True if this node exists.
        """
        return om.MObjectHandle(self.__apiobjects__['MObject']).isValid()

    def __str__(self):
        return self.getName()

    def __hash__(self):
        return _hsh.forNode(self.__apimobject__())

    def __eq__(self, other):
        try:
            other = DependNode(other)
        except:
            return False
        return self.__hash__() == other.__hash__()

    def __repr__(self):
        return "{}('{}')".format(type(self).__name__, str(self))