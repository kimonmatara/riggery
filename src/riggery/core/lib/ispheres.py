"""
Tools for working with implicit spheres.
"""
from typing import Union, Optional

from ..plugtypes import __pool__ as plugs
from ..datatypes import __pool__ as data
from ..nodetypes import __pool__ as nodes
from ..elem import Elem
from . import mixedmode as _mm
from . import mathops as _mo

def projectPointPlugs(
        pointToSnap:'plugs.Point',
        sphereMatrix:'plugs.Sphere',
        innerOrigin:Optional['plugs.Point']=None, *,
        calculateNormal:bool=True
) -> tuple['plugs.Point', Optional['plugs.Vector']]:
    """
    Only for plugs right now, until ``sphereClamp`` is implemented on
    ``data.Vector`` too.

    :param pointToSnap: the point outside the sphere
    :param sphereMatrix: the implicit sphere matrix
    :param innerOrigin: a point inside the sphere towards which to project; uses
        the sphere center if omitted
    :return: Tuple of (surface point, (surface normal at point or None if
        calculateNormal is False)).
    """
    pointToSnap = _mm.conform(pointToSnap,
                              (plugs.Point, data.Point),
                              force=True)

    sphereMatrix = _mm.conform(sphereMatrix, (plugs.Matrix, data.Matrix))

    if innerOrigin is not None:
        innerOrigin = _mm.conform(innerOrigin,
                                  (plugs.Point, data.Point),
                                  force=True)

    invSphereMatrix = sphereMatrix.inverse()

    if innerOrigin is None:
        outPoint = (pointToSnap ^ invSphereMatrix).normal() ^ sphereMatrix
        if calculateNormal:
            outNormal = outPoint.asVector().normal()
        else:
            outNormal = None
        return outPoint, outNormal

    innerOrigin ^= invSphereMatrix
    pointToSnap ^= invSphereMatrix
    rayVector = pointToSnap - innerOrigin
    rayVector = rayVector.sphereClamp(innerOrigin)

    srfPoint = innerOrigin + rayVector
    srfNormal = srfPoint.asVector().normal()

    wSrfPoint = srfPoint ^ sphereMatrix

    if calculateNormal:
        wSrfNormal = (srfNormal * invSphereMatrix.transpose()).normal()
    else:
        wSrfNormal = None

    return wSrfPoint, wSrfNormal

def loopFromTwoPointPlugs(p1:'plugs.Point',
                          p2:'plugs.Point',
                          sphereMatrix:'plugs.Matrix') -> 'plugs.NurbsCurve':
    """
    Generates a NURBS ellipse (just the output) from two points projected onto
    an implicit sphere. The parametric origin of the ellipse will be at the
    surface projection of p1, and the U direction will be towards the projection
    of p2.
    """
    p1 = _mm.conform(p1, (plugs.Point, data.Point), force=True)
    p2 = _mm.conform(p2, (plugs.Point, data.Point), force=True)
    sphereMatrix = _mm.conform(sphereMatrix, (plugs.Matrix, data.Matrix))

    invSphereMatrix = sphereMatrix.inverse()
    localV1 = (p1 ^ invSphereMatrix).asVector()
    localV2 = (p2 ^ invSphereMatrix).asVector()

    circleNormal = localV1.cross(localV2)
    node = nodes['MakeNurbCircle'].createNode()
    node.attr('normal').set((0, 1, 0))
    circleStream = node.attr('outputCurve')

    # Orient
    rmtx = _mm.createOrthoMatrix('y', circleNormal, '-z', localV1).pick(r=1)
    circleStream *= (rmtx * sphereMatrix)

    return circleStream