import re
from typing import Optional, Literal, Union

from ..nodetypes import __pool__ as nodes
DependNode = nodes['DependNode']

import maya.cmds as m

#-----------------------------------------|
#-----------------------------------------|    MAIN CLASS
#-----------------------------------------|

class AnimCurve(DependNode):

    __time_based__ = True

    #-----------------------------|    Broad keyframe inspections

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

    #-----------------------------|    Locate keyframes

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

    def keyExistsAtTime(self, time:Union[int, float]) -> bool:
        kwargs = {'q': True,
                  't' if self.__time_based__ else 'f': (time, time),
                  'tc' if self.__time_based__ else 'fc': True}

        return m.keyframe(str(self), **kwargs) is not None