from contextlib import nullcontext
from typing import Generator

import maya.cmds as m

from ..lib import mixedmode as _mm
from ..lib import names as _nm
from riggery.core.lib.nodetracker import NodeTracker
from riggery.general.functions import short
from ..nodetypes import __pool__ as nodes

def _connectAndLock(srcAttr, destAttr):
    if srcAttr.isMulti():
        for i in srcAttr.indices():
            _connectAndLock(srcAttr[i], destAttr[i])
    elif srcAttr.isCompound():
        for src, dest in zip(srcAttr.children, destAttr.children):
            _connectAndLock(src, dest)
    else:
        srcAttr >> destAttr
        destAttr.lock()

class RemapValue(nodes['DependNode']):

    def sampleColorAt(self, position, once=False):
        """
        :param position: the position (parameter) at which to create a sample
        :param once: return a value, and don't create a new sampling clone;
            defaults to False
        :return: The sample, as an attribute output.
        """
        created = False
        clone = self.findClone(position)
        if clone is None:
            clone = self.createClone(position)
            created = True

        if once:
            out = clone.attr('outColor')()
            if created:
                m.delete(str(clone))
            return out

        return clone.attr('outColor')

    def sampleValueAt(self, position, once:bool=False):
        """
        :param position: the position (parameter) at which to create a sample
        :param once: return a value, and don't create a new sampling clone;
            defaults to False
        :return: The sample, as an attribute output.
        """
        created = False
        clone = self.findClone(position)
        if clone is None:
            clone = self.createClone(position)
            created = True

        if once:
            out = clone.attr('outValue')()
            if created:
                m.delete(str(clone))
            return out

        return clone.attr('outValue')

    def numClones(self) -> int:
        """
        :return: The number of sampling clones connected to this node.
        """
        try:
            return len(self.attr('clones').outputs())
        except AttributeError:
            return 0

    def iterClones(self) -> Generator:
        """
        Yields sampling clones driven by this one.
        """
        if self.hasAttr('clones'):
            for output in self.attr('clones').outputs():
                yield output

    clones = property(fget=iterClones)

    def findClone(self, position):
        """
        Looks for a clone at the specified sample parameter.

        :param position: the parameter at which to retrieve a clone; can be a
            value or plug
        :return: The clone, if one could be found, or None.
        """
        position, _, positionIsPlug = _mm.info(position)

        for clone in self.clones:
            inputValue, inputValueIsPlug \
                = clone.attr('inputValue').getInputOrValue()
            if positionIsPlug == inputValueIsPlug and inputValue == position:
                return clone

    def createClone(self, position):
        """
        Creates a sampling clone at the specified position. Note that this
        doesn't check whether a clone already exists and can be reused; use
        :meth:`getClone` for that instead.

        :param position: the position for which to create a sampling clone
        :return: The clone.
        """
        node = self.duplicate()[0]
        for name in (
            'inputMin',
            'inputMax',
            'outputMin',
            'outputMax',
            'value',
            'color'
        ):
            _connectAndLock(self.attr(name), node.attr(name))
        position >> node.attr('inputValue')
        node.attr('inputValue').lock()

        if not self.hasAttr('clones'):
            self.addAttr('clones', at='message')

        node.addAttr('master',
                     at='message',
                     i=self.attr('clones'),
                     l=True)
        return node

    @short(create='c')
    def getClone(self, position, create:bool=False):
        """
        Creates, or retrieves, a sampling clone at the specified parameter.

        :param position: the parameter at which to retrieve a clone; can be a
            value or plug
        :param create/c: create a clone if one doesn't exist at the specified
            parameters
        :return: The cloned node, or None if one couldn't be found and *create*
            was False.
        """
        clone = self.findClone(position)
        if clone is None:
            if create:
                clone = self.createClone(position)
        return clone