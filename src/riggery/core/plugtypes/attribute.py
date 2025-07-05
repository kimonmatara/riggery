from functools import cached_property
import re
import os
from typing import Union, Optional, Generator, Iterable, Any

import maya.api.OpenMaya as om
import maya.cmds as m
import riggery
import riggery.internal.api2str as _a2s
import riggery.internal.hashing as _hsh
import riggery.internal.plugutil.plugroute as _pr
import riggery.internal.str2api as _s2a
import riggery.core.lib.reorderattrs as _roa
from riggery.core.lib.nativeunits import NativeUnits
import riggery.internal.mfnmatches as _mfm
from riggery.general.functions import short, resolve_flags
from riggery.general.iterables import expand_tuples_lists, \
    without_duplicates
from riggery.internal.plugutil.parseaac import parseAddAttrCmd

from ..elem import Elem, ElemInstError
from ..nodetypes import __pool__ as _nodes
from ..plugtypes import __pool__

uncap = lambda x: x[0].lower()+x[1:]


def _getNodeMObject(nodeArg):
    if isinstance(nodeArg, str):
        return _s2a.getNodeMObject(nodeArg)
    elif isinstance(nodeArg, om.MObject):
        return nodeArg
    elif isinstance(nodeArg, om.MDagPath):
        return nodeArg.node()
    raise TypeError("unsupported signature")

class AttributeMeta(type(Elem)):

    def __call__(cls, *args):
        num = len(args)

        if num == 1:
            # One of:
            # - existing Attribute subclass instance
            # - full string path to the attribute
            # - MPlug instance

            arg = args[0]

            if isinstance(arg, Attribute):
                return arg

            if isinstance(arg, str):
                return cls.fromStr(arg)

            if isinstance(arg, om.MPlug):
                return cls.fromMPlug(arg)

        elif num == 2:
            # A node representation (string, MObject, MDagPath riggery DependNode),
            # and a local attribute representation (string or MObject)

            nodeArg, plugArg = args

            if isinstance(plugArg, str):
                return _nodes['DependNode'](nodeArg).attr(plugArg)

            if isinstance(plugArg, om.MObject):
                return cls.fromMPlug(_getNodeMObject(nodeArg), plugArg)

        raise TypeError('unsupported signature')


class Attribute(Elem, metaclass=AttributeMeta):

    __pool__ = __pool__

    #-----------------------------------------|    Instantiation

    @classmethod
    def fromMPlug(cls, plug:om.MPlug):
        T = cls.__pool__[_pr.getKeyFromMPlug(plug)]
        out = cls._constructInst(T, {'MPlug': plug})
        return out

    @classmethod
    def fromStr(cls, path:str):
        return cls.fromMPlug(
            _s2a.getMPlug(path, firstElem=True, checkShape=True)
        )

    #-----------------------------------------|    Misc navigation

    def node(self):
        """
        :return: The node that owns this attribute.
        """
        return _nodes['DependNode'].fromMObject(self.__apimplug__().node())

    #-----------------------------------------|    Connections

    @classmethod
    def _disconnect(cls, src:'Attribute', dest:'Attribute'):
        if src.isMulti():
            sources = list(src)
        else:
            sources = [src]

        if dest.isMulti():
            dests = list(dest)
        else:
            dests = [dest]

        for source in sources:
            for dest in filter(
                    lambda x: x in source.iterOutputs(plugs=True),
                    dests
            ):
                m.disconnectAttr(str(source), str(dest))

    @classmethod
    def _connect(cls,
                 src:'Attribute',
                 dest:'Attribute',
                 force:bool):
        # Important note: this function *used* to implement *quiet* with a check
        # for src.hasOutput(dest), but sometimes this gave false positives
        # (eminently on curve CV inputs), so it's been discarded; remember this
        # if tempted to roll back in

        # If both are multis, connect at multi level

        if src.isMulti():
            if not dest.isMulti():
                src = src[0]
        else:
            if dest.isMulti():
                dest = dest.nextElement()

        # if src.isMulti():
        #     src = src[0]
        #
        # if dest.isMulti():
        #     dest = dest.nextElement()

        kwargs = {}

        if force:
            kwargs['force'] = True

        with NativeUnits():
            m.connectAttr(str(src), str(dest), **kwargs)

    @short(force='f')
    def connectOutput(self, output, /, force:bool=False):
        """
        Connects from this plug into *output*.

        :param force/f: replace any existing connection; defaults to False
        :return: self
        """
        self._connect(self, Attribute(output), force)
        return self

    def disconnectOutput(self, output):
        """
        :param input: the output to disconnect
        :return: self
        """
        self._disconnect(self, Attribute(output))
        return self

    @short(force='f')
    def connectInput(self, input, /, force:bool=False):
        """
        Connects from *input* plug into this plug.

        :param force/f: replace any existing connection; defaults to False
        :return: self
        """
        self._connect(Attribute(output), self, force)
        return self

    def disconnectInput(self, input):
        """
        :param input: the input to disconnect
        :return: self
        """
        self._disconnect(Attribute(input), self)
        return self

    @short(skipConversionNodes='scn')
    def hasInput(self, input, /, skipConversionNodes:bool=False) -> bool:
        """
        :param skipConversionNodes/scn: skip over ``unitConversion`` nodes;
            defaults to False
        :return: True if *input* is amongst this plug's inputs.
        """
        if isinstance(input, str):
            input = _s2a.getMPlug(input)
        elif isinstance(input, Attribute):
            input = input.__apimplug__()

        return input in self._iterInputPlugs(skipConversionNodes)

    @short(skipConversionNodes='scn')
    def hasOutput(self, output, /, skipConversionNodes:bool=False) -> bool:
        """
        :param skipConversionNodes/scn: skip over ``unitConversion`` nodes;
            defaults to False
        :return: True if *output* is amongst this plug's outputs.
        """
        if isinstance(output, str):
            output = _s2a.getMPlug(output)
        elif isinstance(output, Attribute):
            output = output.__apimplug__()

        return output in self._iterOutputPlugs(skipConversionNodes)

    def _iterInputPlugs(
            self,
            skipConversionNodes:bool
    ) -> Generator[om.MPlug, None, None]:

        thisPlug = self.__apimplug__()

        if thisPlug.isArray:
            destPlugs = [
                thisPlug.elementByLogicalIndex(i) \
                for i in thisPlug.getExistingArrayAttributeIndices()
            ]
        else:
            destPlugs = [thisPlug]

        for destPlug in destPlugs:
            if skipConversionNodes:
                source = destPlug.source()
            else:
                source = destPlug.sourceWithConversion()

            if not source.isNull:
                yield source

    @short(plugs='p',
           skipConversionNodes='scn',
           type='t',
           exactType='et',
           shapes='sh')
    def iterInputs(self, *,
                   plugs:bool=False,
                   shapes:bool=False,
                   type:Optional[Union[str, Iterable[str]]]=None,
                   exactType:bool=False,
                   skipConversionNodes:bool=False) -> Generator:
        """
        :param plugs/p: return plugs rather than nodes; defaults to False
        :param skipConversionNodes/scn: skip over ``unitConversion`` nodes;
            defaults to False
        :param type/t: one or more node type filters; defaults to ``False``
        :param exactType/et: only check against each destination's exact node
            type; defaults to False
        :param shapes/sh: ignored if *plugs* is True; don't auto-expand from
            shapes to transforms; defaults to False
        """
        if type:
            types = without_duplicates(expand_tuples_lists(type))
        else:
            types = []

        for source in self._iterInputPlugs(skipConversionNodes):
            if types or not plugs:
                sourceNodeMObj = source.node()

            if types:
                thisNodeType = om.MFnDependencyNode(sourceNodeMObj).typeName
                if exactType:
                    if thisNodeType not in types:
                        continue

                theseNodeTypes = m.nodeType(thisNodeType,
                                            isTypeName=True,
                                            inherited=True)

                if not any((type in theseNodeTypes \
                            for type in types)):
                    continue

            if plugs:
                yield Attribute.fromMPlug(source)
                continue

            if not shapes:
                if sourceNodeMObj.hasFn(om.MFn.kShape):
                    sourceNodeMObj = om.MFnDagNode(sourceNodeMObj).parent(0)

            yield _nodes['DependNode'].fromMObject(sourceNodeMObj)

    def hasInput(self) -> bool:
        """
        :return: True if this plug has an incoming connection.
        """
        return not self.__apimplug__().sourceWithConversion().isNull

    def hasOutputs(self) -> bool:
        """
        :return: True if this plug has outgoing connections.
        """
        return bool(self.__apimplug__().destinationsWithConversions())

    @property
    def input(self):
        for x in self.iterInputs(plugs=True):
            return x

    def inputs(self, **kwargs) -> list:
        """
        Flat version of :meth:`iterInputs`.
        """
        return list(self.iterInputs(**kwargs))

    def _iterOutputPlugs(
            self,
            skipConversionNodes:bool
    ) -> Generator[om.MPlug, None, None]:

        thisPlug = self.__apimplug__()
        if thisPlug.isArray:
            srcPlugs = [
                thisPlug.elementByLogicalIndex(i) \
                for i in thisPlug.getExistingArrayAttributeIndices()
            ]
        else:
            srcPlugs = [thisPlug]

        for srcPlug in srcPlugs:
            if skipConversionNodes:
                destinations = srcPlug.destinations()
            else:
                destinations = srcPlug.destinationsWithConversions()

            for destination in destinations:
                if not destination.isNull:
                    yield destination

    @short(plugs='p',
           skipConversionNodes='scn',
           type='t',
           exactType='et',
           shapes='sh')
    def iterOutputs(self, *,
                    plugs:bool=False,
                    skipConversionNodes:bool=False,
                    type:Optional[Union[Iterable[str], str]]=None,
                    exactType:bool=False,
                    shapes:bool=False) -> Generator:
        """
        :param plugs/p: return plugs rather than nodes; defaults to False
        :param skipConversionNodes/scn: skip over ``unitConversion`` nodes;
            defaults to False
        :param type/t: one or more node type filters; defaults to ``False``
        :param exactType/et: only check against each destination's exact node
            type; defaults to False
        :param shapes/sh: ignored if *plugs* is True; don't auto-expand from
            shapes to transforms; defaults to False
        """
        if type:
            types = without_duplicates(expand_tuples_lists(type))
        else:
            types = []

        for destination in self._iterOutputPlugs(skipConversionNodes):
            if types or not plugs:
                destNodeMObj = destination.node()

            if types:
                thisNodeType \
                        = om.MFnDependencyNode(destNodeMObj).typeName

                if exactType:
                    if thisNodeType not in types:
                        continue
                else:
                    theseNodeTypes = m.nodeType(
                        thisNodeType,
                        isTypeName=True,
                        inherited=True
                    )
                    if not any((type in theseNodeTypes \
                                for type in types)):
                        continue

            if plugs:
                yield Attribute.fromMPlug(destination)
                continue

            if not shapes:
                if destNodeMObj.hasFn(om.MFn.kShape):
                    destNodeMObj = om.MFnDagNode(destNodeMObj).parent(0)

            yield _nodes['DependNode'].fromMObject(destNodeMObj)

    def outputs(self, **kwargs) -> list:
        """
        Flat version of :meth:`iterOutputs`.
        """
        return list(self.iterOutputs(**kwargs))

    def put(self, other, isPlug:Optional[bool]=None):
        """
        If *other* is an attribute, connects it into this attribute.
        Otherwise, interprets it as a value and sets this attribute to it.

        :param isPlug: if you know whether *other* is a plug or not, specify
            it here to skip some checks; defaults to None
        :return: self
        """
        if isPlug is None:
            try:
                other = Attribute(other)
            except:
                return self.set(other)
            self._connect(other, self, True)
        elif isPlug:
            self._connect(other, self, True)
        else:
            self.set(other)
        return self

    def __rshift__(self, other):
        self._connect(self, Attribute(other), True)

    def __rrshift__(self, other):
        self.put(other)

    def __floordiv__(self, other):
        self._disconnect(self, Attribute(other))

    def __rfloordiv__(self, other):
        self._disconnect(Attribute(other), self)

    @short(inputs='i',
           outputs='o',
           recurse='r')
    def disconnect(self, *,
                   inputs:Optional[bool]=None,
                   outputs:Optional[bool]=None,
                   recurse:bool=False):
        """
        The flags are evaluated by omission. If *inputs* is set to True,
        *outputs* is set to False, etc.

        :param inputs/i: disconnect inputs
        :param outputs/o: disconnect outputs
        :return: self
        """
        inputs = outputs = resolve_flags(inputs, outputs)

        if self.isMulti():
            thesePlugs = list(self)
        else:
            thesePlugs = [self]

        for thisPlug in thesePlugs:
            if inputs:
                for inp in thisPlug.iterInputs(plugs=True):
                    self._disconnect(inp, thisPlug)
            if outputs:
                for outp in thisPlug.iterOutputs(plugs=True):
                    self._disconnect(thisPlug, outp)

        if recurse:
            for child in self.children:
                child.disconnect(inputs=inputs, outputs=outputs)

        return self

    #-----------------------------------------|    Get

    def getInputOrValue(self) -> tuple[Any, bool]:
        """
        Returns a tuple. If this plug has an input, the first element will be
        the input; otherwise, it will be the current value. The second element
        will be True if there was an input, otherwise False.
        """
        inputs = self.inputs(plugs=True)
        if inputs:
            return inputs[0], True
        return self(), False

    def getAttr(self, **kwargs):
        """
        Thin wrapper for :func:`~maya.cmds.getAttr`.
        """
        return m.getAttr(str(self), **kwargs)

    def _getValue(self, *, frame=None, asString=False, **_):
        # Baseline / fallback implementation
        kwargs = {}
        if frame is not None:
            kwargs['time'] = frame
        if asString:
            kwargs['asString'] = True
        return self.getAttr(**kwargs)

    @short(rotateOrder='ro')
    def getValue(self, *,
                 frame:Optional[float]=None,
                 unit:Optional[Union[str, int]]=None,
                 ui:bool=False,
                 asString:bool=False,
                 rotateOrder:Optional[Union[str, int]]=None):
        """
        Returns the value of this plug.

        .. warning::

            In riggery, value setting / getting defaults to native units.

        :param frame: return the value at the specified frame; defaults to
            the current frame
        :param unit: the unit to use; defaults to native units, unless *ui* is
            passed as True
        :param ui: return the value in UI units; defaults to False
        :param rotateOrder/ro: for euler rotation attributes, an override for
            the embedded rotate order (this is not a reordering operation);
            if the attribute is the ``rotate`` channel on a transform node,
            defaults to the node's rotate order; otherwise, defaults to 0
            ('xyz')
        :param asString: for enums, return the enum label rather than the
            integer value; defaults to False
        """
        return self._getValue(frame=frame,
                              unit=unit,
                              ui=ui,
                              asString=asString,
                              rotateOrder=rotateOrder)

    def getDefaultValue(self):
        """
        :return: This attribute's default value, or None if it's undefined.
        """
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        if plug.isCompound:
            return [Attribute.fromMPlug(plug.child(i)).getDefaultValue() \
                    for i in range(plug.numChildren())]
        attr = plug.attribute()
        mfnType = self.__apimfntype__()
        fn = _mfm.fallbackInst(attr, mfnType)[0]
        try:
            return fn.default
        except RuntimeError as exc:
            if 'Object does not exist' in str(exc):
                return None
            raise exc

    def _getDefaultValue(self):
        return self.getDefaultValue()

    def setDefaultValue(self, value):
        plug = self.__apimplug__()
        if not plug.isDynamic:
            raise TypeError(
                "Can't edit default values on non-dynamic attributes"
            )

        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        if plug.isCompound:
            children = [plug.child(i) for i in range(plug.numChildren())]
            for src, child in zip(value, children):
                Attribute.fromMPlug(child).setDefaultValue(src)
        else:
            attr = plug.attribute()
            mfnType = self.__apimfntype__()
            fn = _mfm.fallbackInst(attr, mfnType)[0]
            fn.default = value
        return self

    def _setDefaultValue(self, value):
        return self.setDefaultValue(value)

    defaultValue = dv = property(fget=_getDefaultValue, fset=_setDefaultValue)

    # def getDefaultValue(self): # override this
    #     """
    #     :raise TypeError: This attribute doesn't support default values.
    #     :return: This attribute's default value
    #     """
    #     if self.isMulti():
    #         self = self[0]
    #     return self.__apimfn__().default
    #
    # def setDefaultValue(self, value, apply:bool=False): # override this
    #     """
    #     :param value: the new default value
    #     :param apply: set the current value too; defaults to False
    #     :raise TypeError: The default value can't be changed (e.g. non-dynamic
    #         attribute).
    #     :return: self
    #     """
    #     mplug = self.__apimplug__()
    #     if mplug.isDynamic:
    #         if mplug.isArray:
    #             mplug = mplug.elementByLogicalIndex(0)
    #         mobj = mplug.attribute()
    #         mfnType = self.__apimfntype__()
    #         fn = _mfm.fallbackInst(mobj, mfnType)[0]
    #         fn.default = value
    #         if apply:
    #             self.setValue(value)
    #         return self
    #     raise TypeError("Default value can't be changed")
    #
    # def _getDefaultValue(self):
    #     return self.getDefaultValue()
    #
    # def _setDefaultValue(self, value):
    #     self.setDefaultValue(value)
    #
    # defaultValue = dv = property(_getDefaultValue, _setDefaultValue)

    def resetValue(self, *, quiet:bool=False):
        """
        Resets this value to its defaults.

        :param quiet: don't error if the attribute can't be modified due to
            locking, connections etc.; defaults to False
        :raises TypeError: This attribute doesn't support defaults.
        """
        try:
            self.setValue(self.getDefaultValue())
        except RuntimeError as exc:
            if quiet:
                plug = self.__apiobjects__['MPlug']
                if not plug.isFreeToChange():
                    return self
            raise exc
        return self

    @short(plug='p')
    def get(self, *, plug=False, **kwargs):
        """
        :param plug/p: if True, ignore all other arguments and return
            ``self``; otherwise, defer to :meth:`getValue`; defaults to
            False
        :param \*\*kwargs: forwarded to :meth:`getValue`
        """
        if plug:
            return self
        return self.getValue(**kwargs)

    __call__ = get

    def getFlag(self, flagName:str):
        """
        Thin wrapper for :func:`~maya.cmds.getAttr` in single-flag query mode.
        :param flagName: the flag to query
        :return: The flag name.
        """
        return m.getAttr(str(self), **{flagName:True})

    @short(verbose='v')
    def evaluate(self, verbose:bool=False):
        """
        :param verbose/v: If this flag is used then the results of the
            evaluation(s) is/are printed on stdout.
        :return: self
        """
        kwargs = {}
        if verbose:
            kwargs['verbose'] = True
        m.dgeval(str(self), **kwargs)
        return self

    #-----------------------------------------|    Set

    def setAttr(self, *args, **kwargs):
        """
        Thin wrapper for :func:`maya.cmds.setAttr`.
        """
        return m.setAttr(str(self), *args, **kwargs)

    def _setValue(self, value, **_):
        # This is our base / fallback implementation, so some checks are
        # warranted
        if isinstance(value, (list, tuple)) \
            and all((isinstance(member, (float, int)) for member in value)):
            tensorShape = len(value)

            if tensorShape in (2, 3, 4):
                fn = om.MFnNumericData()
                enumName = f"k{tensorShape}Double"
                typ = getattr(om.MFnNumericData, enumName)
                mobj = fn.create(typ)
                fn.setData(value)
            elif tensorShape == 16:
                fn = om.MFnMatrixData()
                mobj = fn.create()
                fn.set(om.MMatrix(value))
            else:
                # Give up, let Maya error
                self.setAttr(*value)
                return

            self.__apimplug__().setMObject(mobj)
        else:
            self.setAttr(value)

    def setValue(self, value, /,
                 unit:Optional[Union[str, int]]=None,
                 ui:bool=False):
        """
        :param value: the value to set
        :param unit: specifies the unit of *value*; if *ui* is True, defaults
            to the current UI units; otherwise, defaults to native units
            (e.g. radians for rotation)
        :param ui: where *unit* is omitted, default to UI units; defaults to
            False
        :return: self
        """
        self._setValue(value, unit=unit, ui=ui)
        return self

    set = setValue

    @short(recurse='r')
    def setFlag(self, flagName:str, flagValue):
        """
        Atomic variant of :meth:`setFlags`.

        :param flagName: the flag to set
        :param flagValue: the flag value
        :param recurse/r: if this is a compound, perform the edit on its
            children as well; defaults to False
        :return: self
        """
        return self.setFlags(**{flagName:flagValue})

    @short(recurse='r')
    def setFlags(self, *, recurse:bool=False, **kwargs):
        """
        Thin wrapper for :func:`~maya.cmds.setAttr` in strict flag-editing
        mode.

        :param recurse/r: if this is a compound, perform the edit on its
            children as well; defaults to False
        :param \*\*kwargs:
        :return: self
        """
        m.setAttr(str(self), **kwargs)

        if recurse and self.isCompound():
            for child in self.children:
                child.setFlags(**kwargs)
        return self

    #-----------------------------------------|    Get / set

    value = property(getValue, setValue, resetValue)

    #-----------------------------------------|    Lock

    def setLocked(self, state:bool, recurse:bool=False):
        """
        :param state: the lock state
        :param recurse: if this is a compound, set the lock state on the
            children too; defaults to False
        :return: self
        """
        if self.isMulti():
            if recurse:
                for i in self.indices():
                    self[i].setLocked(state, recurse=recurse)
                return self
            else:
                self = self[0]

        if recurse and self.isCompound():
            for child in self.children:
                child.setLocked(state, recurse=True)
            return self

        plug = self.__apimplug__()
        plug.isLocked = state

        return self

    def isLocked(self) -> bool:
        """
        :return: True if this attribute is locked.
        """
        return self.__apimplug__().isLocked

    @short(recurse='r')
    def lock(self, recurse:bool=False):
        """
        Locks this attribute.

        :param recurse: if this is a compound, lock the children too.
        :return: self
        """
        return self.setLocked(True, recurse)

    @short(recurse='r', force='f')
    def unlock(self, *, recurse:bool=False, force:bool=False):
        """
        Unlocks this attribute.

        :param recurse/r: if this is a compound, unlock its children too;
            defaults to False
        :param force/f: if this is the child in a compound, and the parent is
            locked, unlock the parent and lock the siblings; defaults to False
        :return: self
        """
        self.setFlags(lock=False, recurse=recurse)
        if force:
            parent = self.parent
            if parent and parent.isLocked():
                parent.unlock()
                for sibling in self.siblings:
                    sibling.lock()
        return self

    #-----------------------------------------|    Show / hide

    @short(recurse='r',
           keyable='k',
           channelBox='cb',
           force='f')
    def show(self,
             recurse:bool=False,
             force:bool=False,
             keyable:Optional[bool]=None,
             channelBox:Optional[bool]=None):
        """
        :param recurse/r: if this is a compound, show its children too;
            defaults to False
        :param force/f: if this is the child of a compound, and the parent
            is hidden, unhide the parent and hide all the siblings; defaults
            to False
        :param keyable/k: make the attribute keyable; defaults to True
        :param channelBox/cb: make the attribute settable, but not keyable;
            defaults to False
        :return: self
        """
        if keyable is None:
            if channelBox is None:
                keyable = True
            else:
                keyable = not channelBox

        kwargs = {'keyable': keyable, 'channelBox': not keyable}
        self.setFlags(recurse=recurse, **kwargs)

        if force:
            parent = self.parent
            if parent and parent.isHidden():
                parent.show()
                for sibling in self.siblings:
                    sibling.hide()

        return self

    @short(recurse='r')
    def hide(self, recurse:bool=False):
        """
        Turns off 'keyable' and 'channelBox' on this attribute so that it
        no longer appears in the channel box at all.

        :param recurse/r: if this is a compound, hide its children too;
            defaults to False
        :return: self
        """
        return self.setFlags(keyable=False, channelBox=False, recurse=recurse)

    def isHidden(self) -> bool:
        """
        :return: True if this attribute is not visible in the channel box.
        """
        return not (self.getFlag('k') or self.getFlag('cb'))

    #-----------------------------------------|    Enable / disable

    @short(recurse='r',
           channelBox='cb',
           keyable='k')
    def enable(self,
               recurse:bool=False,
               channelBox:Optional[bool]=None,
               keyable:Optional[bool]=None):
        """
        Unlocks and reveals this attribute in the channel box.
        :param recurse/r: unlock and reveal child attributes too; defaults to
            False
        :param channelBox/cb: make the attribute settable in the channel box;
            defaults to False
        :param keyable/k: make the attribute keyable; defaults to True
        :return: self
        """
        self.show(channelBox=channelBox, keyable=keyable, recurse=recurse)
        self.unlock(recurse=recurse)
        return self

    @short(recurse='r')
    def disable(self, recurse:bool=False):
        """
        Hides and locks this attribute.

        :param recurse/r: if this is a compound, hide and lock its children too;
            defaults to False
        :return: self
        """
        return self.setFlags(channelBox=False,
                             keyable=False,
                             lock=True,
                             recurse=recurse)

    @short(recurse='r')
    def release(self, recurse:bool=False):
        """
        Unlocks this attribute and disconnects any inputs, so that it's free
        to edit.

        :param recurse/r: if this is a compound, release its children too;
            defaults to False
        :return: self
        """
        self.unlock(recurse=recurse)
        self.disconnect(recurse=recurse, inputs=True)
        return self

    #-----------------------------------------|    Multi

    def __getitem__(self, logicalIndex:int):
        if logicalIndex >= 0:
            plug = self.__apimplug__().elementByLogicalIndex(logicalIndex)
            return Attribute.fromMPlug(plug)
        return list(self)[logicalIndex]

    def __len__(self) -> int:
        if self.isMulti():
            return len(self.indices())
        raise TypeError("not a multi")

    def __iter__(self) -> Generator['Attribute', None, None]:
        plug = self.__apimplug__()
        if plug.isArray:
            indices = plug.getExistingArrayAttributeIndices()
            if indices:
                for index in indices:
                    yield Attribute.fromMPlug(
                        plug.elementByLogicalIndex(index)
                    )
        else:
            raise TypeError("Not a multi array")

    def isMulti(self) -> bool:
        """
        :return: True if this is a 'multi' array.
        """
        return self.__apiobjects__['MPlug'].isArray

    def indexMatters(self) -> bool:
        """
        :return: The value of the ``indexMatters`` flag, if this is a multi.
        """
        return om.MFnAttribute(
            self.__apimplug__().attribute()
        ).indexMatters

    def getArrayIndices(self) -> list[int]:
        """
        Alias: `indices`
        :return: A list of this multi attribute's indices.
        """
        return list(self.__apimplug__().getExistingArrayAttributeIndices())

    indices = getArrayIndices

    @short(contiguous='c', reuse='re')
    def nextIndex(self, *, contiguous:bool=False, reuse:bool=False) -> int:
        """
        :param contiguous/c: return element indices which aren't part of the
            'existing' range, rather than just adding to the end; defaults to
            False
        :param reuse/re: return the first existing element index which is free
            to connect; defaults to False
        """
        plug = self.__apimplug__()
        indices = plug.getExistingArrayAttributeIndices()

        if indices:
            if reuse:
                for index in indices:
                    elem = plug.elementByLogicalIndex(index)
                    if elem.isFreeToChange() == 0:
                        return index
            if contiguous:
                fullRange = list(range(indices[-1]+1))
                for index in fullRange:
                    if index not in indices:
                        return index
            return indices[-1] + 1
        return 0

    @short(contiguous='c', reuse='re')
    def nextElement(self, *, contiguous:bool=False, reuse:bool=False) -> int:
        """
        :param contiguous/c: return element indices which aren't part of the
            'existing' range, rather than just adding to the end; defaults to
            False
        :param reuse/re: return the first existing element index which is free
            to connect; defaults to False
        """
        plug = self.__apimplug__()
        indices = plug.getExistingArrayAttributeIndices()

        if indices:
            if reuse:
                for index in indices:
                    elem = plug.elementByLogicalIndex(index)
                    if elem.isFreeToChange() == 0:
                        return Attribute.fromMPlug(
                            plug.elementByLogicalIndex(index)
                        )
            if contiguous:
                fullRange = list(range(indices[-1]+1))
                for index in fullRange:
                    if index not in indices:
                        return Attribute.fromMPlug(
                            plug.elementByLogicalIndex(index)
                        )
            return Attribute.fromMPlug(
                plug.elementByLogicalIndex(indices[-1] + 1)
            )
        return Attribute.fromMPlug(plug.elementByLogicalIndex(0))

    def numElements(self, evaluate:bool=False) -> int:
        """
        Must be called on a 'multi' array.

        :param evaluate: evaluate the elements for accuracy; defaults to False
        :return: The number of elements in the array.
        """
        plug = self.__apimplug__()
        if evaluate:
            return plug.evaluateNumElements()
        return plug.numElements()

    def lastElement(self):
        return self[self.numElements()-1]

    def isElement(self) -> bool:
        """
        :return: True if this an element in a 'multi' array.
        """
        return self.__apiobjects__['MPlug'].isElement

    def index(self) -> int:
        """
        This must be called on the element of a 'multi' array.
        :return: The index of this element.
        """
        return self.__apimplug__().logicalIndex()

    def toMulti(self):
        """
        If this is an element in a multi, returns the root. Otherwise, if
        it's the root of the multi, returns ``self``. Otherwise, errors.
        """
        if self.isMulti():
            return self
        return self.__apimplug__().array()

    @short(lock='l', start='s')
    def feedMulti(self, sources, lock=False, start=0):
        """
        Convenience method. Inputs each of the sources in *sources* into the
        elements of this multi.
        """
        for i, source in enumerate(sources, start=start):
            source >> self[i]
        if lock:
            self.lock(recurse=True)
        return self

    def clearMulti(self):
        """
        This must be called on the root of a multi. Clears out all elements,
        breaking any connections.
        """
        _self = str(self)
        for index in self.indices():
            m.removeMultiInstance(f"{_self}[{index}]", b=True)
        return self

    def __delitem__(self, logicalIndex:int):
        """
        Wraps :func:`maya.cmds.removeMultiInstance` with *b=True*.
        :param logicalIndex: the index of the 'multi' element to remove
        """
        m.removeMultiInstance(str(self[logicalIndex]), b=True)

    #-----------------------------------------|    Compound

    def numChildren(self) -> int:
        """
        This must be a compound plug.

        :return: The number of children in this compound.
        """
        return self.__apimplug__().numChildren()

    def isCompound(self) -> bool:
        """
        :return: True if this is a compound plug.
        """
        return self.__apimplug__().isCompound

    def isChild(self) -> bool:
        """
        :return: True if this is a child of a compound attribute.
        """
        return self.__apimplug__().isChild

    def iterChildren(self) -> Generator:
        """
        Yields compound children.

        Property: ``.children``

        :raises TypeError: This isn't a compound attribute.
        """
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)
        if plug.isCompound:
            for i in range(plug.numChildren()):
                yield Attribute.fromMPlug(plug.child(i))

    children = property(fget=iterChildren)

    def attr(self, attrName:str):
        """
        :param attrName: the name of the child attribute to retrieve
        :return: The child attribute.
        """
        try:
            return Attribute.fromMPlug(
                _s2a.getMPlugOnMPlug(self.__apimplug__(), attrName)
            )
        except RuntimeError as exc:
            _exc = str(exc)
            if 'Object does not exist' in _exc:
                raise AttributeError(f'Attribute not found: {attrName}')
            raise exc

    def __getattr__(self, item):
        return self.attr(item)

    def getChildren(self) -> list:
        """
        :raises TypeError: This isn't a compound attribute.
        :return: The children of this compound, in a list.
        """
        if self.isMulti():
            self = self[0]
        return list(self.iterChildren())

    def splitInput(self, quiet:bool=False):
        """
        If this is a compound with a parent-level connection, connects-up
        the children too.

        :param quiet: suppress any errors; defaults to False
        :return: ``self``
        """
        if self.isMulti():
            self = self[0]

        if self.isCompound():
            inputs = self.inputs(plugs=True)
            if inputs:
                input = inputs[0]
                try:
                    for src, dest in zip(input.children, self.children):
                        src >> dest
                except Exception as exc:
                    if quiet:
                        pass
                    else:
                        raise exc
        else:
            if quiet:
                return self
            raise TypeError("Not a compound")

        return self

    def getParent(self) -> Optional['Attribute']:
        """
        :return: The compound parent of this attribute, if any.
        """
        if self.isChild():
            return Attribute.fromMPlug(self.__apimplug__().parent())

    parent = property(getParent)

    def iterSiblings(self) -> Generator['Attribute', None, None]:
        """
        This must be a child in a compound attribute.

        Yields siblings.
        """
        for child in self.parent.children:
            if child != self:
                yield child

    def getSiblings(self) -> list['Attribute']:
        """
        Flag version of :meth:`iterSiblings`.
        """
        return list(self.iterSiblings())

    siblings = property(iterSiblings)

    #-----------------------------------------|    API

    def __apimplug__(self) -> om.MPlug:
        plug = self.__apiobjects__['MPlug']
        attr = self.__apiobjects__.setdefault(
            'MObject',
            plug.attribute()
        )
        if om.MObjectHandle(attr).isValid():
            node = plug.node()
            if om.MObjectHandle(node).isValid():
                return plug
        raise ElemInstError("Object removed")

    def __apimobject__(self) -> om.MObject:
        return self.__apimplug__().attribute()

    def __apimfntype__(self) -> type:
        apiType = self.__apiobjects__.setdefault(
            'MObject',
            self.__apiobjects__['MPlug'].attribute()
        ).apiType()
        matches = _mfm.MFNMATCHES[apiType]
        if len(matches) == 1:
            return matches[0]
        raise TypeError(f"No unambiguous MFn match")

    def __apimfn__(self) -> om.MFnBase:
        """
        :raises TypeError: No unambiguous MFn match. If you encounter this
            error, the method should be overriden to pick a single MFn type
            around which to instantiate.
        """
        return _mfm.fallbackInst(self.__apimobject__(),
                                 self.__apimfntype__())[0]

    def exists(self) -> bool:
        """
        :return: True if this plug exists.
        """
        mPlug = self.__apiobjects__['MPlug']
        attrMObject = mPlug.attribute()
        if om.MObjectHandle(attrMObject).isValid():
            nodeMObject = mPlug.node()
            return om.MObjectHandle(nodeMObject).isValid()
        return False

    #-----------------------------------------|    Type wrangling

    def asType(self, T:type):
        """
        Assigns the type *T* to this instance. This is an in-place operation,
        but ``self`` is returned as a convenience.
        """
        self.__class__ = T
        return self

    def attributeType(self) -> Optional[str]:
        """
        :return: This attribute's type, as returned by
            :class:`om.MFnAttribute.getAddAttrCmds`.
        """
        return self.getAddAttrCmdFlags().get('attributeType')

    def dataType(self) -> Optional[str]:
        """
        :return: This attribute's data type, as returned by
            :class:`om.MFnAttribute.getAddAttrCmds`.
        """
        return self.getAddAttrCmdFlags().get('dataType')

    def type(self) -> str:
        """
        Uses ``getAttr(type=True)``.
        """
        return self.getFlag('type')

    @short(inherited='i', classNames='cn')
    def virtualType(self,
                    inherited:bool=False,
                    classNames:bool=False) -> Union[str, list[str]]:
        """
        Similar to :func:`~maya.cmds.nodeType`, except returns riggery attribute
        types.

        :param inherited/i: return a reverse MRO; defaults to False
        :param classNames/cn: return class names rather than lowercase type
             names; defaults to False
        """
        path = _pr.getPathFromKey(self.__class__.__name__)
        if not inherited:
            out = path[-1]
            if not classNames:
                out = uncap(out)
            return out

        if not classNames:
            path = list(map(uncap, path))
        return path

    @cached_property
    def aaInfo(self) -> dict:
        return parseAddAttrCmd(
            om.MFnAttribute(
                self.__apiobjects__['MPlug'].attribute()
            ).getAddAttrCmd(True)
        )

    def getAddAttrCmdFlags(self) -> dict:
        """
        :return: A dictionary of flags that would have to be used with
            :func:`maya.cmds.addAttr` to recreate this attribute.
        """
        return self.aaInfo.copy()

    def isTyped(self) -> bool:
        """
        :return: True if this is a typed attribute.
        """
        return self.__apiobjects__['MPlug'
            ].attribute().hasFn(om.MFn.kTypedAttribute)

    def isGeneric(self) -> bool:
        """
        :return: True if this is a generic attribute.
        """
        return self.__apiobjects__['MPlug'
            ].attribute().hasFn(om.MFn.kGenericAttribute)

    def isDynamic(self) -> bool:
        """
        :return: True if this is a dynamic (user-added) attribute.
        """
        return self.__apiobjects__['MPlug'].isDynamic

    def isAnimatableDynamic(self):
        """
        :return: True if this is a dynamic attribute that can be exposed for
            keying.
        """
        if self.isDynamic():
            typ = self.attributeType()

            if re.match(r"^(float|double|long|short)[23]$", typ):
                return True

            return typ in set(['bool', 'long', 'short', 'enum', 'time',
                               'float', 'double', 'doubleAngle',
                               'doubleLinear'])
        return False

    #-----------------------------------------|    Reordering

    def canBeReordered(self) -> bool:
        """
        :return: True if this attribute can be reordered. Reorderable
            attributes are user-added scalars visible in the Channel Box.
        """
        try:
            _roa.ReorderableAttr(self.__apimobject__(), self.attrName())
            return True
        except _roa.AttrReorderError:
            return False

    def sendAbove(self, otherAttr:str):
        """
        Sends this attribute above *otherAttr* in the Channel Box stack.

        :param otherAttr: the local name of the other attribute
        :return: self
        """
        node = self.__apimplug__().node()
        result = _roa.reorderAttrs(node, [self.longName(), otherAttr])
        self.__apiobjects__ = {'MPlug': result[0]}
        return self

    def sendBelow(self, otherAttr:str):
        """
        Sends this attribute above *otherAttr* in the Channel Box stack.

        :param otherAttr: the local name of the other attribute
        :return: self
        """
        node = self.__apimplug__().node()
        result = _roa.reorderAttrs(node, [otherAttr, self.longName()])
        self.__apiobjects__ = {'MPlug': result[1]}
        return self

    #-----------------------------------------|    Authoring

    @classmethod
    def _createStubContent(cls):
        clsname = cls.__name__
        pname = cls.mro()[1].__name__
        lines = [
            'from ..plugtypes import __pool__ as plugs', '', '', ''
            f"class {clsname}(plugs['{pname}']):", '',
            '    ...'
        ]
        return '\n'.join(lines)

    @classmethod
    def _getStubFilePath(cls) -> str:
        pdir = os.path.join(
            os.path.dirname(riggery.__file__),
            'core', cls.__pool__.__pool_package__.split('.')[-1]
        )

        filename = f"{uncap(cls.__name__)}.py"
        return os.path.join(pdir, filename)

    #-----------------------------------------|    Sections

    def isSectionAttr(self) -> bool:
        """
        :return: ``True`` if this looks like a 'section' enum attribute.
        """
        return False

    #-----------------------------------------|    Proxy attributes

    def toProxySource(self):
        """
        If this is a proxy attribute, returns the original. Otherwise, returns
        this attribute.

        :raises RuntimeError: This is a proxy attribute, but its input
            connection to the original is broken.
        """
        if self.isProxy():
            out = self.input
            if out is None:
                raise RuntimeError("Broken proxy link.")
            return out
        return self

    def getProxySource(self):
        """
        If this is a proxy for another attribute, return the original
        attribute. Otherwise, returns None.

        :raises RuntimeError: This is a proxy attribute, but its input
            connection to the original is broken.
        """
        if self.isProxy():
            out =  self.input
            if out is None:
                raise RuntimeError("Broken proxy link.")
            return out

    def iterProxies(self) -> Generator:
        """
        Yields proxies for this attribute elsewhere.
        """
        for output in self._iterOutputPlugs():
            if output.isProxy:
                yield Attribute.fromMPlug(output)

    def getProxies(self) -> list:
        """
        Flat version of :meth:`iterProxies`.
        """
        return list(self.iterProxies())

    proxies = property(iterProxies)

    def isProxy(self) -> bool:
        """
        :return: True if this attribute is a proxy for another.
        """
        return self.__apimplug__().isProxy

    def getOrig(self):
        """
        If this is a proxy attribute, returns the attribute for which it is a
        proxy. Otherwise, returns this attribute.
        """
        if self.isProxy():
            return self.inputs(plugs=True)[0]
        return self

    def createProxy(self, node, **kwargs):
        """
        Atomic version of :meth:`createProxies`.
        """
        return self.createProxies([node], **kwargs)[0]

    @short(longName='ln', shortName='sn', section='s')
    def createProxies(self,
                      nodes:Iterable,
                      longName=None,
                      shortName=None, *,
                      section=None):
        """
        Creates a proxy for this attribute on each specified node.

        :param \*nodes: the node(s) on which to create proxy attributes,
            packed or unpackeds
        :param longName/ln: an optional override for the attribute long name
        :param shortName/sn: an optional override for the attribute short name
        :return: The generated proxy attributes, in a list.
        """
        kwargs = self.getAddAttrCmdFlags()

        if shortName:
            kwargs['shortName'] = shortName

        elif longName:
            try:
                del(kwargs['shortName'])
            except KeyError:
                pass
            kwargs['longName'] = longName

        try:
            accessName = kwargs['longName']
        except kwargs:
            accessName = kwargs['shortName']

        try:
            del(kwargs['parent'])
        except:
            pass

        kwargs['proxy'] = str(self)

        out = []

        for node in nodes:
            _node = str(node)
            m.addAttr(_node, **kwargs)
            inst = Attribute(f"{_node}.{accessName}")
            if section is not None:
                sectionInst = node.sections.add(section)
                inst = sectionInst.collect(accessName)[0]
            out.append(inst)
        return out

    @classmethod
    @short(lock='l')
    def linkAxisVectorAttrs(cls, axisAttr, vectorAttr, lock=True):
        """
        Links an attribute of the type created by :meth:`addAxisAttr` with one
        created by :meth:`addTripleAttr`, such that selecting a different axis
        on the enum will output the relevant basis vector.

        :param axisAttr: the axis enum attribute
        :param vectorAttr: the compound attribute to output to
        :param lock/l: lock the vector attribute after driving it; defaults
            to True
        """
        choice = _nodes['Choice'].createNode()
        for i, (axisName, axisVec) in enumerate(zip(
                ('posX', 'posY', 'posZ', 'negX', 'negY', 'negZ'),
                ([1, 0, 0], [0, 1, 0], [0, 0, 1], [-1, 0, 0], [0, -1, 0], [0, 0, -1])
        )):
            attr = choice.addAttr(axisName, dt='double3')
            attr.set(axisVec)
            attr.lock()
            attr >> choice.attr('input')[i]
        axisAttr >> choice.attr('selector')
        choice.attr('output') >> vectorAttr
        if lock:
            vectorAttr.lock(recurse=True)

    #-----------------------------------------|    Repr

    def attrName(self, longName:bool=False) -> str:
        """
        :param longName: return the long attribute name; defaults to ``False``
        :return: The attribute name.
        """
        fn = om.MFnAttribute(self.__apimobject__())
        return fn.name if longName else fn.shortName

    def shortName(self) -> str:
        """
        :return: The short name of this attribute.
        """
        return self.attrName()

    def longName(self) -> str:
        """
        :return: The long name of this attribute.
        """
        return self.attrName(longName=True)

    def __str__(self):
        return _a2s.fromMPlug(self.__apimplug__())

    def __repr__(self):
        try:
            return "{}({})".format(type(self).__name__, repr(str(self)))
        except ElemInstError:
            return "<deleted plug>"

    def __hash__(self):
        return _hsh.forMPlug(self.__apimplug__())

    def __eq__(self, other):
        return self.__hash__() == Attribute(other).__hash__()