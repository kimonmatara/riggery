from typing import Iterable, Union, Optional, Literal

from ..nodetypes import __pool__ as nodes
from . import __pool__ as plugs
from riggery.general.numbers import floatrange

from ..lib.mixedmode import MixedScalar, MixedVector, info
Texture2d = nodes['Texture2d']

import maya.cmds as m


class RampArrayInterface:
    """
    Index-based. Yields tuples of position (input or value), color
    (input or value).
    """

    #-------------------------------------|    Init

    def __init__(self, node):
        self._node = node

    def node(self):
        return self._node

    #-------------------------------------|    Get

    def __getitem__(self, index:int):
        self.jolt()
        slot = self.plug[index]

        return (slot.attr('position').getInputOrValue()[0],
                slot.attr('color').getInputOrValue()[0])

    @property
    def plug(self):
        self.jolt()
        return self._node.attr('colorEntryList')

    def indices(self) -> list[int]:
        return self.plug.indices()

    def jolt(self):
        """
        If the array is in that messy 'uninitialized' state, (i.e. no entries),
        force-creates the default color entries.
        """
        plug = self._node.attr('colorEntryList')

        if not plug.indices():
            plug[0].attr('position').set(0.0)
            plug[0].attr('color').set((0, 0, 0))

            plug[1].attr('position').set(1.0)
            plug[1].attr('color').set((1, 1, 1))

        return self

    def __len__(self):
        return len(self.plug)

    def __iter__(self):
        for slot in self.plug:
            yield (slot.attr('position').getInputOrValue()[0],
                   slot.attr('color').getInputOrValue()[0])

    #-------------------------------------|    Set

    def __setitem__(self, index, content:tuple[MixedScalar, MixedVector]):
        slot = self.plug[index]
        slot.attr('position').setOrConnect(content[0], f=1)
        slot.attr('color').setOrConnect(content[1], f=1)

    #-------------------------------------|    Queries

    def findSlotFromPosition(self, position) -> Optional['plugs.Attribute']:
        p, _, pIsPlug = info(position)

        for slot in self.plug:
            tp, tpIsPlug = slot.attr('position').getInputOrValue()

            if ((pIsPlug and tpIsPlug)
                or not (pIsPlug or tpIsPlug)) and p == tp:
                yield slot

    def findIndexFromPosition(self, position) -> Optional[int]:
        slot = self.findSlotFromPosition(position)

        if slot is not None:
            return slot.index()

    #-------------------------------------|    Del

    def __delitem__(self, index):
        m.removeMultiInstance("{}[{}]".format(self.plug, index), b=True)

    #-------------------------------------|    Reset

    def reset(self):
        plug = self._node.attr('colorEntryList')
        plug.clearMulti()

        self[0] = 0.0, (0.0, 0.0, 0.0)
        self[1] = 1.0, (1.0, 1.0, 1.0)

        return self

#-----------------------------------------|
#-----------------------------------------|    MAIN CLASS
#-----------------------------------------|

class Ramp(Texture2d):
    """
    Uses the self.array interface for quick manipulations.
    """

    #-------------------------------------|    Array interface

    @property
    def array(self):
        return RampArrayInterface(self)

    #-------------------------------------|    Sampling

    def distributeColorSamples(self, number:int) -> list['plugs.Vector']:
        return [self.sampleColorAt(x) for x in floatrange(0, 1, number)]
    
    def distributeValueSamples(self, number:int) -> list['plugs.Vector']:
        """
        Same as :meth:`distributeColorSamples`, but only returns the R
        components.
        """
        return [self.sampleValueAt(x) for x in floatrange(0, 1, number)]

    def sampleColorAt(self, position:MixedScalar) -> 'plugs.Vector':
        return self.initClone(position).attr('outColor')

    def sampleValueAt(self, position:MixedScalar) -> 'plugs.Float':
        """
        Same as :meth:`sampleColorAt`, but only returns the R components.
        """
        return self.initClone(position).attr('outColorR')

    @property
    def samplingDimension(self) -> Optional[Literal['u', 'v']]:
        type = self.attr('type')()

        if type == 0:
            return 'v'

        elif type == 1:
            return 'u'

    def findClone(self, position:MixedScalar) -> Optional['Ramp']:
        """
        :raises TypeError: can only perform sampling if 'type' is set to u or v
        """
        dimension = self.samplingDimension

        if dimension not in 'uv':
            raise TypeError(
                "can only perform sampling if 'type' is set to u or v"
            )

        position, _, positionIsPlug = info(position)

        for clone in self.tags.get('clones', []):
            thisPosition, thisPositionIsPlug = clone.attr(
                f'{dimension}Coord'
            ).getInputOrValue()

            if (((thisPositionIsPlug and positionIsPlug)
                or not (thisPositionIsPlug or positionIsPlug))
                    and position == thisPosition):
                return clone

    def initClone(self, position:MixedScalar) -> 'Ramp':
        """
        Creates, or retrieves, a clone for the specified position.
        :raises TypeError: can only perform sampling if 'type' is set to u or v
        """
        clone = self.findClone(position)

        if clone is None:
            clone = self.createClone(position)

        return clone

    def createClone(self, position:MixedScalar) -> 'Ramp':
        """
        :raises TypeError: can only perform sampling if 'type' is set to u or v
        """
        dimension = self.samplingDimension

        if dimension not in 'uv':
            raise TypeError(
                "can only perform sampling if 'type' is set to u or v"
            )

        node = self.duplicate()[0]

        for name in ('interpolation',
                     'colorEntryList',
                     'uWave',
                     'vWave',
                     'noise',
                     'noiseFreq',
                     'hueNoise',
                     'satNoise',
                     'valNoise',
                     'hueNoiseFreq',
                     'satNoiseFreq',
                     'valNoiseFreq',
                     'defaultColor',
                     'colorGain',
                     'colorOffset',
                     'alphaGain',
                     'alphaOffset',
                     'invert',
                     'uvCoord'):
            src = self.attr(name)
            dest = node.attr(name)
            state = src.getState(input=True, value=True)
            dest.setState(state, input=True, value=True)

        node.attr(f'{dimension}Coord').setOrConnect(position, f=1).lock()
        cloneList = self.tags.get('clones', [])
        cloneList.append(node)
        self.tags['clones'] = cloneList

        return node