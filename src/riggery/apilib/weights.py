import maya.api.OpenMaya as om
import maya.cmds as m
import numpy as np
from ..internal import api2str as _a2s
from .dag import toShape, getParent
from .geo import createMeshFromSurfaceCage, iterPointPositions

#-----------------------------------------|
#-----------------------------------------|    PLUG I/O
#-----------------------------------------|

def readWeights(plug:om.MPlug, length:int, default:float) -> list[float]:
    """
    The fastest Python method I could come up with to read 1D weight plugs.

    :param plug: the 'multi' plug to read from
    :param length: the expected number of weight entries
    :param default: the default value to use for missing entries (typically 1.0
        or 0.0)
    :return: The weights, in a list.
    """
    values = [default] * length

    arrayHandle = plug.asMDataHandle()
    arrayDataHandle = om.MArrayDataHandle(arrayHandle)

    while not arrayDataHandle.isDone():
        logicalIndex = arrayDataHandle.elementLogicalIndex()

        if logicalIndex < length:
            values[logicalIndex] = arrayDataHandle.outputValue().asFloat()

        arrayDataHandle.next()

    plug.destructHandle(arrayHandle)

    return values

def writeWeights(plug:om.MPlug, weights:list[float], chunkSize:int=10000):
    """
    Writes into deformer weights plug. All values are written in index
    sequence, but the array is not resized if it has legacy overflow.

    :param values: the weight values (floats)
    :param chunkSize: the size of the ``setAttr`` chunks (to prevent Python
        memory issues); defaults to 10000
    """
    totalLength = len(weights)

    if totalLength == 0:
        return

    plug = _a2s.fromMPlug(plug)

    for startIndex in range(0, totalLength, chunkSize):
        endIndex = min(startIndex + chunkSize, totalLength)
        mayaEndIndex = endIndex - 1
        chunkPath = f"{plug}[{startIndex}:{mayaEndIndex}]"
        chunkData = weights[startIndex:endIndex]
        m.setAttr(chunkPath, *chunkData)

#-----------------------------------------|
#-----------------------------------------|    WEIGHT SMOOTHING
#-----------------------------------------|

def smoothWeights(weights:list[float],
                  mesh:om.MDagPath,
                  iterations:int=3,
                  strength:float=0.5) -> list[float]:
    """
    Performs weighted Laplacian smoothing on the given weights.

    :param weights: the weights
    :param mesh: the mesh that carries the weights
    :param iteration: the number of times to run a smooth; defaults to 3
    :param strength: controls the blend between the original value and the
        neighbourhood average (where 0 = no smoothing and 1 = full replacement);
        defaults to 0.5
    :return: The smoothed weights, in a list.
    """
    meshShapeDagPath = toShape(mesh)
    meshFn = om.MFnMesh(meshShapeDagPath)

    numVerts = meshFn.numVertices
    numInfluences = len(weights) // numVerts
    w = np.array(weights, dtype=np.float64).reshape(numVerts, numInfluences)

    it = om.MItMeshVertex(meshFn.object())
    neighbours = [list(x.getConnectedVertices()) for x in it]

    for _ in range(iterations):
        smoothed = w.copy()

        for i, nbrs in enumerate(neighbours):
            if not nbrs:
                continue
            neighbourAvg = w[nbrs].mean(axis=0)
            smoothed[i] = (1.0 - strength) * w[i] + strength * neighbourAvg

        w = smoothed

    return w.ravel().tolist()

#-----------------------------------------|
#-----------------------------------------|    UTIL
#-----------------------------------------|

def barycentricCoords(p: om.MPoint,
                      a: om.MPoint,
                      b: om.MPoint,
                      c: om.MPoint) -> tuple[float, float, float]:
    v0 = b - a
    v1 = c - a
    v2 = p - a

    d00 = v0 * v0
    d01 = v0 * v1
    d11 = v1 * v1
    d20 = v2 * v0
    d21 = v2 * v1

    denom = d00 * d11 - d01 * d01
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1.0 - v - w

    return u, v, w

def _asMesh(geo:om.MDagPath) -> tuple[om.MDagPath, bool]:
    geoShapeDagPath = toShape(geo)
    geoShapeMObj = geoShapeDagPath.node()

    if geoShapeMObj.hasFn(om.MFn.kMesh):
        return geoShapeDagPath, False

    if geoShapeMObj.hasFn(om.MFn.kNurbsSurface):
        return createMeshFromSurfaceCage(geoShapeDagPath), True

    raise TypeError("expected mesh or NURBS surface")

#-----------------------------------------|
#-----------------------------------------|    WEIGHT REMAPPING
#-----------------------------------------|

def remapWeights(weights:list[float],
                 srcGeo:om.MDagPath,
                 destGeo:om.MDagPath,
                 worldSpace:bool=False,
                 smoothIterations:int=0,
                 smoothStrength:float=0.5) -> list[float]:

    #---------------------------|    Prep

    srcShapeDagPath, deleteSrc = _asMesh(srcGeo)
    destShapeDagPath, deleteDest = _asMesh(destGeo)

    try:
        srcMeshFn = om.MFnMesh(srcShapeDagPath)
        destMeshFn = om.MFnMesh(destShapeDagPath)

        #-----------------------|    Cook

        result = []
        weights = list(weights)

        numInfluences = len(weights) // srcMeshFn.numVertices
        srcWeights = np.array(weights, dtype=np.float64).reshape(-1,
                                                                 numInfluences)

        space = om.MSpace.kWorld if worldSpace else om.MSpace.kObject

        for pt in iterPointPositions(destGeo, worldSpace):
            closestPt, faceIdx = srcMeshFn.getClosestPoint(pt, space)
            vtxIds = srcMeshFn.getPolygonVertices(faceIdx)
            verts = [srcMeshFn.getPoint(i, space) for i in vtxIds[:3]]

            bary = barycentricCoords(closestPt, *verts)
            w = sum(b * srcWeights[i] for b, i in zip(bary, vtxIds[:3]))
            result.extend(w.tolist())

        #-----------------------|    Smooth

        if smoothIterations and smoothStrength:
            result = smoothWeights(result,
                                   destShapeDagPath,
                                   smoothIterations,
                                   smoothStrength)

    finally:
        if deleteSrc:
            om.MGlobal.deleteNode(getParent(srcShapeDagPath).node())

        if deleteDest:
            om.MGlobal.deleteNode(getParent(destShapeDagPath).node())

    return result