from typing import Iterator

import maya.api.OpenMaya as om
import maya.cmds as m

from .dag import toShape, getParent, setParent
from .transform import getMatrix, setMatrix

def createMeshFromSurfaceCage(surface:om.MDagPath) -> om.MDagPath:
    """
    Builds a mesh from the cage of the given NURBS surface. The mesh will be
    generated under a matched transform at the same level as *surface*.

    :return: The DAG path to the mesh shape or transform node.
    """
    srfShapeDagPath = toShape(surface)
    srfFn = om.MFnNurbsSurface(srfShapeDagPath)

    numU = srfFn.numCVsInU
    numV = srfFn.numCVsInV

    points = om.MPointArray()

    for i in range(numU):
        for j in range(numV):
            points.append(srfFn.cvPosition(i, j, om.MSpace.kPreTransform))

    polyCounts  = om.MIntArray()
    polyConnects = om.MIntArray()

    for i in range(numU - 1):
        for j in range(numV - 1):
            polyCounts.append(4)
            polyConnects.append(i * numV + j)
            polyConnects.append(i * numV + j + 1)
            polyConnects.append((i + 1) * numV + j + 1)
            polyConnects.append((i + 1) * numV + j)

    meshFn = om.MFnMesh()
    meshFn.create(points, polyCounts, polyConnects)

    meshShapeMObject = meshFn.object()
    meshShapeDagPath = om.MDagPath.getAPathTo(meshShapeMObject)

    meshXfDagPath = om.MDagPath(meshShapeDagPath)
    meshXfDagPath.pop()

    # Reparent
    srfXfDagPath = getParent(srfShapeDagPath)
    setParent(meshXfDagPath, getParent(srfXfDagPath))

    matrix = getMatrix(srfXfDagPath)
    setMatrix(meshXfDagPath, matrix)

    return meshShapeDagPath

def iterPointPositions(geo:om.MDagPath,
                       worldSpace:bool=False) -> Iterator[om.MPoint]:
    """
    Yields positions for any 'point'-like components on *geo*.
    """
    geoShapeDagPath = toShape(geo)
    itr = om.MItGeometry(geoShapeDagPath)
    out = (x.position() for x in itr)

    if worldSpace:
        matrix = geoShapeDagPath.inclusiveMatrix()
        out = (x * matrix for x in out)

    return list(out)