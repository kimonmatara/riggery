import re
from typing import Optional, Literal, Union, Iterator, TypeAlias

from ..nodetypes import __pool__ as nodes
from riggery.general.functions import short
DependNode = nodes['DependNode']

import maya.cmds as m

TangentType:TypeAlias = [
    "auto",
    "autocustom",
    "autoease",
    "automix",
    "clamped",
    "fast",
    "flat",
    "linear",
    "plateau",
    "slow",
    "spline",
    "step",
    "stepnext"
]

#-----------------------------------------|
#-----------------------------------------|    INTERFACE
#-----------------------------------------|

class Adjunct:

    #-----------------------------|    Init

    def __init__(self, node:'AnimCurve'):
        self._node = node

    #-----------------------------|    Properties

    def node(self) -> 'AnimCurve':
        return self._node


class Keyframe(Adjunct): # by index

    #-----------------------------|    Init

    def __init__(self, node:'AnimCurve', index:int):
        super().__init__(node)
        self._index = index

    @property
    def index(self) -> int:
        return self._index

    def exists(self) -> bool:
        return self.node().keyExistsAtIndex(self.index)

    #-----------------------------|    Time

    def getTime(self) -> Optional[float]:
        return self.node().getKeyTimeAtIndex(self.index)

    time = property(getTime)

    #-----------------------------|    Value

    def getValue(self) -> Optional[float]:
        return self.node().getKeyValueAtIndex(self.index)

    value = property(getValue)

    #-----------------------------|    Repr

    def __repr__(self):
        return "{}.keyframes[{}]".format(repr(self.node()), self.index)


class Keyframes(Adjunct): # by index

    #-----------------------------|    Get

    def indices(self):
        return self.node().getKeyIndices()

    def values(self):
        return self.node().getKeyValues()

    def times(self):
        return self.node().getKeyTimes()

    def __iter__(self):
        for index in self.indices():
            yield Keyframe(self.node(), index)

    def __len__(self):
        return self.node().numKeys()

    def findAtTime(self, time:float) -> Optional['Keyframe']:
        index = self.node().getKeyIndexAtTime(time)

        if index:
            return Keyframe(self.node(), index)

    def __getitem__(self, index:int):
        if self.node().keyExistsAtIndex(index):
            return Keyframe(self.node(), index)

        raise IndexError(f"no keyframe at index {index}")

    def __repr__(self):
        return "{}.keyframes".format(repr(self.node()))

#-----------------------------------------|
#-----------------------------------------|    MAIN CLASS
#-----------------------------------------|

class AnimCurve(DependNode):

    __time_based__ = True

    @property
    def keyframes(self):
        return Keyframes(self)

    #-----------------------------|    Keyframe querying

    def getKeyTimes(self) -> list[float]:
        args = (str(self),)
        kwargs = {'q': True, 'tc' if self.__time_based__ else 'fc':True}
        out = m.keyframe(*args, **kwargs)

        if out is None:
            return []

        return out

    def getKeyValues(self) -> list[float]:
        args = (str(self),)
        kwargs = {'q': True, 'vc': True}
        out = m.keyframe(*args, **kwargs)

        if out is None:
            return []

        return out

    def getKeyIndices(self) -> list[int]:
        args = (str(self),)
        kwargs = {'q': True, 'iv': True}
        out = m.keyframe(*args, **kwargs)

        if out is None:
            return []

        return out

    def numKeys(self) -> int:
        return self.__apimfn__().numKeys

    def getKeyTimeAtIndex(self, index:int) -> Optional[float]:
        kwargs = {'q': True,
                  'index': (index, index),
                  'tc' if self.__time_based__ else 'fc': True}
        result = m.keyframe(str(self), **kwargs)

        if result is not None:
            return result[0]

    def getKeyValueAtIndex(self, index:int) -> Optional[float]:
        kwargs = {'q': True,
                  'index': (index, index),
                  'vc': True}
        result = m.keyframe(str(self), **kwargs)

        if result is not None:
            return result[0]

    def getKeyIndexAtTime(self, time:float) -> Optional[int]:
        kwargs = {'q': True,
                  't' if self.__time_based__ else 'f': (time, time),
                  'iv': True}
        result = m.keyframe(str(self), **kwargs)

        if result is not None:
            return result[0]

    def getKeyValueAtTime(self,
                          time:Union[float, int]) -> Optional[float]:
        kwargs = {'q': True,
                  't' if self.__time_based__ else 'f': (time, time),
                  'vc': True}

        result = m.keyframe(str(self), **kwargs)

        if result is not None:
            return result[0]

    def getKeyTimeAtIndex(self, index:int) -> Optional[float]:
        kwargs = {'q': True,
                  'i': (index, index),
                  'tc' if self.__time_based__ else 'fc': True}

        result = m.keyframe(str(self), **kwargs)

        if result is not None:
            return result[0]

    def keyExistsAtIndex(self, index:int) -> bool:
        kwargs = {'q': True,
                  'index': (index, index),
                  'iv': True}

        return m.keyframe(str(self), **kwargs) is not None

    def keyExistsAtTime(self, time:Union[int, float]) -> bool:
        kwargs = {'q': True,
                  't' if self.__time_based__ else 'f': (time, time),
                  'tc' if self.__time_based__ else 'fc': True}

        return m.keyframe(str(self), **kwargs) is not None

    #-----------------------------|    Weighted

    def getWeighted(self) -> bool:
        return self.__apimfn__().isWeighted

    def setWeighted(self, state:bool):
        m.keyTangent(str(self), e=True, weightedTangents=True)

    weighted = property(getWeighted, setWeighted)

    #-----------------------------|    Editing

    @short(inTangentType='itt',
           outTangentType='ott',
           minimizeRotation='mr')
    def setKey(self,
               time:float,
               value:float,
               inTangentType:Optional[TangentType]=None,
               outTangentType:Optional[TangentType]=None,
               minimizeRotation:Optional[bool]=None):

        kwargs = {'t' if self.__time_based__ else 'f': (time, time),
                  'value': value}

        if inTangentType is not None:
            kwargs['itt'] = inTangentType

        if outTangentType is not None:
            kwargs['ott'] = outTangentType

        if minimizeRotation is not None:
            kwargs['mr'] = minimizeRotation

        m.setKeyframe(str(self), **kwargs)
        return self

    @short(preserveCurveShape='pcs')
    def insertKey(self, time:float, preserveCurveShape:Optional[bool]=None):
        kwargs = {'t' if self.__time_based__ else 'f': (time, time),
                  'insert': True}

        m.setKeyframe(str(self), **kwargs)
        return self