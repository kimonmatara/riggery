"""Miscellaneous tools for maths operations that mix values and attributes."""

from pprint import pprint
from typing import Union, Any, Optional

from .nurbsutil import cvIndexToAnchorIndex
from ..datatypes import __pool__ as _data
from ..plugtypes import __pool__ as _plugs
from ..nodetypes import __pool__ as _nodes

import maya.cmds as m

from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists
from riggery.internal.str2api import getMPlug
from .nativeunits import nativeunits

#-----------------------------------------|
#-----------------------------------------|    BASELINE TOOLS
#-----------------------------------------|

def isSingleVector(item:Any) -> bool:
    """
    :return: True if *item* represents a single vector value or plug.
    """
    if isinstance(item, (list, tuple)):
        return len(item) == 3 \
            and all((isinstance(member, (float, int)) for member in item))
    if isinstance(item, _plugs['Attribute']):
        return getattr(item, '__shape__', None) == 3
    if isinstance(item, str):
        try:
            plug = _plugs['Attribute'](item)
        except:
            return False
        return getattr(plug, '__shape__', None) == 3
    return False

def getPlug(item):
    """
    If *item* is a plug, returns a :class:`~riggery.core.plugtypes.Attribute`
    instance; otherwise, returns None.
    """
    Attribute = _plugs['Attribute']
    if isinstance(item, Attribute):
        return item
    if isinstance(item, str):
        try:
            return Attribute.fromStr(item)
        except:
            pass

@short(force='f')
def getValue(item,
             preferredTypes:Union[None, type, tuple[type], list[type]]=None,
             force:bool=False):
    if isinstance(item, str):
        try:
            item = _plugs['Attribute'](item)
        except:
            return item
        if preferredTypes is not None:
            item = conform(item, preferredTypes, force=force)
        return item

    if isinstance(item, _plugs['Attribute']):
        if preferredTypes is not None:
            item = conform(item, preferredTypes, force=force)
        return item

    if preferredTypes is not None:
            item = conform(item, preferredTypes, force=force)
    return item

@short(force='f')
def valueAndPlug(item:Any,
                 preferredTypes:Union[None, type, tuple[type], list[type]]=None,
                 force:bool=False) -> tuple[Any, Optional['_nodes.Attribute']]:
    """
    :param item: the item to examine
    :param preferredTypes: one or more preferred plug or data types to cast to;
        defaults to None
    :param force/f: use one of the preferred types even if *item* is already
        a plug or data type; defaults to False
    :return: If *item* is a plug, a tuple of (current value, plug); otherwise,
        (current value, None).
    """
    item, _, itemIsPlug = info(item, preferredTypes, force)
    if itemIsPlug:
        return item(), item
    return item, None

@short(force='f')
def info(
        item,
        preferredTypes:Union[None, type, tuple[type], list[type]]=None,
        force:bool=False
) -> tuple[Any, Optional[int], bool]:
    """
    :param item: the item to inspect and conform
    :param preferredTypes: one or more preferred plug or data types to cast to;
        defaults to None
    :param force/f: use one of the preferred types even if *item* is already
        a plug or data type; defaults to False
    :return: A tuple of <conformed item>, <math shape> (None for scalars),
        <is plug>.
    """
    if preferredTypes is None:
        dataTypes = {}
        plugTypes = {}
    else:
        if not isinstance(preferredTypes, (tuple, list)):
            preferredTypes = [preferredTypes]

        dataTypes = {}
        plugTypes = {}

        for T in preferredTypes:
            if issubclass(T, _plugs['Attribute']):
                pool = plugTypes
            else:
                pool = dataTypes

            pool.setdefault(getattr(T, '__shape__', None), []).append(T)

    if isinstance(item, (float, int)):
        for T in dataTypes.get(None, []):
            try:
                item = T(item)
            except:
                continue
            break
        return item, None, False

    if isinstance(item, (list, tuple)):
        isTensorType = isinstance(item, _data['Tensor'])
        shape = len(item)
        if isTensorType and not force:
            return item, len(item), False

        if isTensorType or all((isinstance(x, (float, int)) for x in item)):
            for T in dataTypes.get(shape, []):
                try:
                    item = T(item)
                except:
                    continue
                break
            return item, shape, False
        raise TypeError(f"can't conform item {item}")

    if isinstance(item, str):
        try:
            item = _plugs['Attribute'](item)
        except:
            raise TypeError(f"not an attribute: {item}")

        try:
            shape = item.__shape__
        except AttributeError:
            raise TypeError(f"not a math attribute: {item}")

        for T in plugTypes.get(shape, []):
            item = item.asType(T)
            break

        return item, shape, True

    if isinstance(item, _plugs['Math']):
        if not force:
            return item, item.__shape__, True

        shape = item.__shape__

        for T in plugTypes.get(shape, []):
            item = item.asType(T)
            break

        return item, shape, True

    raise TypeError(f"Can't conform item {item} to a math type.")

def conform(item,
            preferredTypes:Union[None, type, tuple[type], list[type]]=None,
            /, *,
            force=False) -> Any:
    """
    Calls :func:`info` and returns only the first element (the conformed item).
    """
    return info(item, preferredTypes=preferredTypes, force=force)[0]

#-----------------------------------------|
#-----------------------------------------|    MISC OPERATIONS
#-----------------------------------------|

def blendScalars(scalar1, scalar2, weight=0.5):
    """
    :param scalar1: the first scalar (value or plug)
    :param scalar2: the second scalar (value or plug)
    :param weight: the weight towards *scalar2* (value or plug); defaults to 0.5
    :return: The blended scalar.
    """
    scalar1, _, isPlug1 = info(scalar1)
    scalar2, _, isPlug2 = info(scalar2)
    weight, _, wIsPlug = info(weight)

    if isPlug1 or isPlug2 or wIsPlug:
        node = _nodes['BlendTwoAttr'].createNode()
        node.attr('input')[0].put(scalar1, isPlug1)
        node.attr('input')[1].put(scalar2, isPlug2)
        node.attr('attributesBlender').put(weight, wIsPlug)

        return node.attr('output')

    scalar1 = float(scalar1)
    scalar2 = float(scalar2)
    weight = float(weight)

    return scalar1 + ((scalar2-scalar1) * weight)

#-----------------------------------------|
#-----------------------------------------|    MATRIX CONSTRUCTORS
#-----------------------------------------|

def createScaleMatrix(*scalars):
    """
    Creates a _data or 'live' matrix given one or three scalar values or plugs.
    """
    scalars = expand_tuples_lists(*scalars)
    states = [info(scalar) for scalar in scalars]
    scalars = [state[0] for state in states]
    hasPlugs = any((state[2] for state in states))

    num = len(scalars)
    if num == 1:
        scalars *= 3
        states *= 3

    if hasPlugs:
        node = _nodes['FourByFourMatrix'].createNode()
        for field, scalar, state in zip(
                ('in00', 'in11', 'in22'),
                scalars,
                states
        ):
            node.attr(field).put(scalar, state[2])
        return node.attr('output')

    matrix = _data['Matrix']()
    matrix[0], matrix[5], matrix[10] = scalars
    return matrix

def createIdentityMatrix(plug=False):
    """
    Creates an identity (null) matrix.
    :param plug: return a plug rather than a _data object; defaults to False
    """
    if plug:
        return _nodes['HoldMatrix'].createNode().attr('outMatrix')
    return _data['Matrix']()

@short(plug='p')
def _createOrthoMatrix(aimAxis,
                       aimVector,
                       upAxis,
                       upVector,
                       w=None, *,
                       plug=None):
    """
    Creates an orthonormal matrix. Works with plugs or values. If any of the
    arguments are plugs, the output will also be a plug.

    :param aimAxis: the aim axis, for example, 'y', '-z' etc.
    :param aimVector: the vector to map to the aim axis
    :param upAxis:mthe aim axis, for example, 'y', '-z' etc.
    :param upVector: the vector to map to the up axis
    :param w: an optional translation component
    :param plug/p: force a plug output even if all the arguments are
        values; defaults to ``None``
    :return: The result matrix.
    """
    swapAim = '-' in aimAxis
    aimAxis = aimAxis.lower().strip('-')

    swapUp = '-' in upAxis
    upAxis = upAxis.lower().strip('-')

    if aimAxis == upAxis:
        raise ValueError("Aim axis same as up axis")

    #---------------------------------|    Parse args

    hard = False
    Vector = _data['Vector']
    Point = _data['Point']

    aimVectorPlug = getPlug(aimVector)
    if aimVectorPlug is None:
        aimVector = Vector(aimVector)
    else:
        aimVector = aimVectorPlug
        hard = True

    upVectorPlug = getPlug(upVector)
    if upVectorPlug is None:
        upVector = Vector(upVector)
    else:
        upVector = upVectorPlug
        hard = True

    if w is not None:
        wPlug = getPlug(w)
        if wPlug is None:
            w = Point(w)
        else:
            w = wPlug
            hard = True

    hard = hard or plug

    #---------------------------------|    Build

    consec = aimAxis + upAxis in 'xyzxy'

    if swapAim:
        aimVector *= -1.0

    if swapUp:
        upVector *= -1.0

    if consec:
        thirdVector = aimVector ^ upVector
        upVector = thirdVector ^ aimVector
    else:
        thirdVector = upVector ^ aimVector
        upVector = aimVector ^ thirdVector

    thirdAxis = [ax for ax in 'xyz' if ax not in aimAxis + upAxis][0]

    if hard:
        ff = _nodes['FourByFourMatrix'].createNode()
        for ax, vector in zip((aimAxis, upAxis, thirdAxis),
                              (aimVector, upVector, thirdVector)):
            vector >> getattr(ff, ax)

        if w is not None:
            w >> ff.w

        return ff.attr('output')

    out = _data['Matrix']()
    for ax, vector in zip((aimAxis, upAxis, thirdAxis),
                          (aimVector, upVector, thirdVector)):
        setattr(out, ax, vector)

    if w is not None:
        out.w = w

    return out

def _createOrthoMatrixFromTwoVectors(aimVector, upVector, *, w=None):
    aimVector, _, aimVectorIsPlug = info(aimVector, _data['Vector'])
    upVector, _, upVectorIsPlug = info(upVector, _data['Vector'])
    thirdVector = aimVector ^ upVector
    upVector = thirdVector ^ aimVector

    if w is not None:
        w, _, wIsPlug = info(w, _data['Point'])
    else:
        wIsPlug = False

    if aimVectorIsPlug or upVectorIsPlug or wIsPlug:
        ff = _nodes['FourByFourMatrix'].createNode()
        aimVector >> ff.x
        upVector >> ff.y
        thirdVector >> ff.z
        if w is not None:
            w >> ff.w
        return ff.attr('output')
    else:
        matrix = _data['Matrix']()
        matrix.x = aimVector
        matrix.y = upVector
        matrix.z = thirdVector
        if w is not None:
            matrix.w = w
        return matrix

def _createOrthoMatrixFromFreeAxes(aimAxis, aimVector,
                                   upAxis, upVector, w=None):
    axisMatrix = _createOrthoMatrixFromTwoVectors(aimAxis, upAxis)
    vectorsMatrix = _createOrthoMatrixFromTwoVectors(aimVector, upVector)
    matrix = axisMatrix.inverse() * vectorsMatrix
    if w is not None:
        matrix *= w.asMatrix()
    return matrix

def _createOrthoMatrixFromLetterAxes(aimAxis, aimVector,
                                     upAxis, upVector, w=None):
    """
    Creates an orthonormal matrix. Works with plugs or values. If any of the
    arguments are plugs, the output will also be a plug.

    :param aimAxis: the aim axis, for example, 'y', '-z' etc.
    :param aimVector: the vector to map to the aim axis
    :param upAxis:mthe aim axis, for example, 'y', '-z' etc.
    :param upVector: the vector to map to the up axis
    :param w: an optional translation component
    :return: The result matrix.
    """
    swapAim = '-' in aimAxis
    aimAxis = aimAxis.lower().strip('-')

    swapUp = '-' in upAxis
    upAxis = upAxis.lower().strip('-')

    if aimAxis == upAxis:
        raise ValueError("Aim axis same as up axis")

    #---------------------------------|    Parse args

    hard = False

    aimVectorPlug = getPlug(aimVector)
    if aimVectorPlug is None:
        aimVector = _data['Vector'](aimVector)
    else:
        aimVector = aimVectorPlug
        hard = True

    upVectorPlug = getPlug(upVector)
    if upVectorPlug is None:
        upVector = _data['Vector'](upVector)
    else:
        upVector = upVectorPlug
        hard = True

    if w is not None:
        wPlug = getPlug(w)
        if wPlug is None:
            w = _data['Point'](w)
        else:
            w = wPlug
            hard = True

    #---------------------------------|    Build

    consec = aimAxis + upAxis in 'xyzxy'

    if swapAim:
        aimVector *= -1.0

    if swapUp:
        upVector *= -1.0

    if consec:
        thirdVector = aimVector ^ upVector
        upVector = thirdVector ^ aimVector
    else:
        thirdVector = upVector ^ aimVector
        upVector = aimVector ^ thirdVector

    thirdAxis = [ax for ax in 'xyz' if ax not in aimAxis+upAxis][0]

    # Assemble
    if hard:
        ff = _nodes['FourByFourMatrix'].createNode()
        for ax, vector in zip((aimAxis, upAxis, thirdAxis),
                              (aimVector, upVector, thirdVector)):
            vector >> getattr(ff, ax)

        if w is not None:
            w >> ff.w

        return ff.attr('output')
    else:
        out = _data['Matrix']()
        for ax, vector in zip((aimAxis, upAxis, thirdAxis),
                              (aimVector, upVector, thirdVector)):
            setattr(out, ax, vector)

        if w is not None:
            out.w = w

        return out

def createOrthoMatrix(*args, w=None):
    """
    :param \*args: One of the following:
        -   Two arguments: aimVector:Vector, upVector:Vector
        -   Four arguments:
            -   aimAxis:str, aimVector:Vector, upAxis:str,
                upVector:Vector, or:
            -   aimAxis:Vector, aimVector:Vector, upAxis:Vector,
                upVector:Vector
    :param w: an optional translate component
    :return: The matrix.
    """
    num = len(args)
    if num == 2:
        return _createOrthoMatrixFromTwoVectors(*args, w=w)

    if num == 4:
        arg1, arg2, arg3, arg4 = args
        if isinstance(arg1, str) and isinstance(arg3, str):
            return _createOrthoMatrixFromLetterAxes(arg1, arg2, arg3, arg4, w)
        else:
            if all((_info[1] == 3 \
                    for _info in map(info, (arg1, arg2, arg3, arg4)))):
                return _createOrthoMatrixFromFreeAxes(arg1, arg2, arg3, arg4, w)
    raise TypeError("unsupported signature")