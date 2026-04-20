from itertools import chain, pairwise

from ..datatypes import __pool__ as data
from . mixedmode import MixedVector, MixedQuaternion, asVector, createOrthoMatrix
from typing import Iterator, Iterable

# def carriers(tangents:Iterable[MixedVector]) -> Iterator[MixedQuaternion]:
#     tangents = iter(tangents)
#     first = next(tangents, None)
#
#     if first is not None:
#         first, firstIsPlug = asVector(first)
#
#         if firstIsPlug:
#             yield first().rotateTo(first)
#
#         else:
#             yield data['Quaternion']()
#
#         tangents = chain([first], (x[0] for x in map(asVector, tangents)))
#
#         for a, b in pairwise(tangents):
#             yield a.rotateTo(b)
#
# def prepNormal(normal:MixedVector, tangent:MixedVector):
#     normal, normalIsPlug = asVector(normal)
#     tangent, tangentIsPlug = asVector(tangent)
#
#     if ((normalIsPlug and tangentIsPlug)
#             or not (normalIsPlug or tangentIsPlug)):
#         return normal.rejectFrom(tangent)
#
#     # Calculate the offset
#     _normal = normal() if normalIsPlug else normal
#     _tangent = tangent() if tangentIsPlug else tangent
#
#     _tangentOrtho = _tangent.rejectFrom(_normal, True)
#     offset = _tangentOrtho.rotateTo(_tangent)
#
#     if normalIsPlug:
#         offset *= _normal.rotateTo(normal)
#     else:
#         offset *= _tangent.rotateTo(tangent)
#
#     return normal * offset
#
# def transport(normal:MixedVector,
#               tangents:Iterable[MixedVector],
#               snap=True) -> Iterator[MixedVector]:
#     tangents = iter(tangents)
#     firstTangent = next(tangents, None)
#
#     if firstTangent is not None:
#         if snap:
#             firstTangent, firstTangentIsPlug = asVector(firstTangent)
#             normal, normalIsPlug = asVector(normal)
#
#             if normalIsPlug or firstTangentIsPlug:
#                 _normal = normal() if normalIsPlug else normal
#                 _firstTangent = (firstTangent() if firstTangentIsPlug
#                                  else firstTangent)
#                 _firstTangentOrtho = _firstTangent.rejectFrom(_normal)
#                 normal *= _firstTangentOrtho.rotateTo(_firstTangent)
#             else:
#                 mag = normal.length()
#                 normal = normal.rejectFrom(firstTangent).normal() * mag

def oneShot(normal, tangent):
    normal, normalIsPlug = asVector(normal)
    tangent, tangentIsPlug = asVector(tangent)

    if normalIsPlug:
        if tangentIsPlug:
            _normal = normal()
            _tangent = tangent()

            _iniMatrix = createOrthoMatrix(_tangent, _normal).pick(r=True)

            carrier = _tangent.rotateTo(tangent)
            bishopMatrix = _iniMatrix * carrier

            localNormal = normal * bishopMatrix.inverse()
            localNormal = localNormal.rejectFrom((1, 0, 0))

            return localNormal.normal() * bishopMatrix


    # if (normalIsPlug or tangentIsPlug):
    #     _normal = normal() if normalIsPlug else normal
    #     _tangent = tangent() if tangentIsPlug else tangent
    #
    #     iniMatrix = createOrthoMatrix('z', _normal,
    #                                   'x', _tangent).pick(rotate=1)
    #
    #
