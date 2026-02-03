from typing import Union, Iterable

from ..nodetypes import __pool__ as _nodes
from ..datatypes import __pool__ as _data
from ..plugtypes import __pool__ as _plugs
from .mixedmode import MixedScalar, info
from . import names as _nm

import maya.cmds as m

def normalize(weights:Iterable[MixedScalar],
              ) -> Union[list[float], list[_plugs['Float']]]:
    """
    Normalizes all the weights into the 0.0 -> 1.0 range. If all the weights
    are at zero, sets them all to 1.0.

    If there are any plugs in *weights*, the output will be a list of plugs.
    Otherwise, the output will be a list of floats.
    """
    weightInfo = [info(weight) for weight in weights]
    num = len(weights)
    weights = [x[0] for x in weightInfo]
    hasPlugs = any((x[2] for x in weightInfo))

    if hasPlugs:
        total = weights[0].sum(*weights[1:])

        with _nm.Name('patchbay'):
            pb = _nodes['Network'].createNode()
            one = pb.addAttr('one', k=1, dv=1, l=True, at='double')

        atZero = total < 1e-4

        return [atZero.ifElse(one, w / total) for w in weights]

    total = sum(weights)

    if total == 0.0:
        return [1.0] * num

    return [x / total for x in weights]