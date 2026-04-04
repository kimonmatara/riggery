from typing import Optional
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
                  geo:om.MDagPath,
                  iterations:int=3,
                  strength:float=0.5) -> list[float]:
    """
    Performs weighted Laplacian smoothing on the given weights.

    :param weights: the weights
    :param geo: the NURBS surface or mesh against which to perform the smoothing
    :param iteration: the number of times to run a smooth; defaults to 3
    :param strength: controls the blend between the original value and the
        neighbourhood average (where 0 = no smoothing and 1 = full replacement);
        defaults to 0.5
    :return: The smoothed weights, in a list.
    """
    if not (iterations or strength):
        return list(weights)

    meshShapeDagPath, deleteMesh = _asMesh(geo)

    try:
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
        out = w.ravel().tolist()

    finally:
        if deleteMesh:
            om.MGlobal.deleteNode(getParent(meshShapeDagPath).node())

    return out

#-----------------------------------------|
#-----------------------------------------|    BARYCENTRIC WEIGHT REMAPPING
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

def remapWeightsBary(weights:list[float],
                     srcGeo:om.MDagPath,
                     destGeo:om.MDagPath,
                     worldSpace:bool=False) -> list[float]:
    """
    Performs barycentric remapping of a weight list. This can sometimes get
    noisy, so consider following it up with :func:`smoothWeights`.
    """
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

    finally:
        if deleteSrc:
            om.MGlobal.deleteNode(getParent(srcShapeDagPath).node())

        if deleteDest:
            om.MGlobal.deleteNode(getParent(destShapeDagPath).node())

    return result

#-----------------------------------------|
#-----------------------------------------|    WEIGHT REMAPPING BY-UV
#-----------------------------------------|

def _buildUVTriangleArrays(meshFn:om.MFnMesh, uvSet:Optional[str]=None):
    uArray = om.MFloatArray()
    vArray = om.MFloatArray()

    if uvSet is None:
        uvSet = tuple()
    else:
        uvSet = (uvSet,)

    uArray, vArray = meshFn.getUVs(*uvSet)
    uv = np.array([(uArray[i], vArray[i])
                   for i in range(len(uArray))], dtype=np.float64)

    triA, triB, triC = [], [], []
    vtxA, vtxB, vtxC = [], [], []

    for faceIdx in range(meshFn.numPolygons):
        vtxIds = meshFn.getPolygonVertices(faceIdx)
        uvIds = [meshFn.getPolygonUVid(faceIdx, k, *uvSet)
                 for k in range(len(vtxIds))]

        for k in range(1, len(vtxIds) - 1):
            triA.append(uv[uvIds[0]])
            triB.append(uv[uvIds[k]])
            triC.append(uv[uvIds[k+1]])
            vtxA.append(vtxIds[0])
            vtxB.append(vtxIds[k])
            vtxC.append(vtxIds[k+1])

    return (np.array(triA), np.array(triB), np.array(triC),
            np.array(vtxA), np.array(vtxB), np.array(vtxC))

def _barycentric2DBatch(p:np.ndarray,
                        a:np.ndarray,
                        b:np.ndarray,
                        c:np.ndarray):
    """
    Vectorised barycentric coords for one point p against N triangles.

    :param p: (2,)
    :param a: (N, 2)
    :param b: (N, 2)
    :param c: (N, 2)
    :return: (N, 3) bary coords.
    """
    v0 = b - a # (N, 2)
    v1 = c - a # (N, 2)
    v2 = p - a # (N, 2)

    d00 = (v0*v0).sum(axis=1)
    d01 = (v0*v1).sum(axis=1)
    d11 = (v1*v1).sum(axis=1)
    d20 = (v2*v0).sum(axis=1)
    d21 = (v2*v1).sum(axis=1)

    denom = d00*d11 - d01*d01
    valid = np.abs(denom) > 1e-10

    bv = np.where(valid, (d11*d20 - d01*d21)
                  / np.where(valid, denom, 1.0), -1.0)

    bw = np.where(valid, (d00*d21 - d01*d20)
                  / np.where(valid, denom, 1.0), -1.0)

    bu = 1.0 - bv - bw

    return np.stack([bu, bv, bw], axis=1) # (N, 3)

def remapWeightsUV(weights:list[float],
                   srcGeo:om.MDagPath,
                   destGeo:om.MDagPath,
                   srcUVSet:Optional[str]=None,
                   destUVSet:Optional[str]=None) -> list[float]:
    """
    Remaps weights in UV space. Where available this should be preferred over
    :func:`remapWeightsBary`, as it's less noisy and fairly quick.
    """
    #---------------------------|    Prep

    srcShapeDagPath, deleteSrc = _asMesh(srcGeo)
    destShapeDagPath, deleteDest = _asMesh(destGeo)

    try:
        srcMeshFn = om.MFnMesh(srcShapeDagPath)

        #-----------------------|    Cook

        numInfluences = len(weights) // srcMeshFn.numVertices
        srcWeights = np.array(weights,
                              dtype=np.float64).reshape(-1, numInfluences)
        triA, triB, triC, vtxA, vtxB, vtxC = _buildUVTriangleArrays(srcMeshFn,
                                                                    srcUVSet)

        # Collect dest UVs
        destUVs = []
        it = om.MItMeshVertex(destShapeDagPath)

        if destUVSet is None:
            destUVSet = tuple()
        else:
            destUVSet = (destUVSet,)

        for vtx in it:
            destUVs.append(vtx.getUV(*destUVSet))

        destUVs = np.array(destUVs, dtype=np.float64)

        result = np.zeros((len(destUVs), numInfluences), dtype=np.float64)

        for i, p in enumerate(destUVs):
            bary = _barycentric2DBatch(p, triA, triB, triC)
            inside = np.all(bary >= 0, axis=1)
            hit = np.argmax(inside)

            if not inside[hit]:
                continue

            bu, bv, bw = bary[hit]

            result[i] = (bu*srcWeights[vtxA[hit]] +
                         bv*srcWeights[vtxB[hit]] +
                         bw*srcWeights[vtxC[hit]])

        resultList = result.ravel().tolist()

    finally:
        if deleteSrc:
            om.MGlobal.deleteNode(getParent(srcShapeDagPath).node())

        if deleteDest:
            om.MGlobal.deleteNode(getParent(destShapeDagPath).node())

    return resultList

def remapWeightsClosest(weights:list[float],
                        srcGeo:om.MDagPath,
                        destGeo:om.MDagPath,
                        worldSpace:bool=False,
                        k:int=6) -> list[float]:
    """
    :param k: the number of source vertices that contribute to each destination
        vertex's weights; defaults to 6
    """
    #---------------------------|    Prep

    if worldSpace:
        space = om.MSpace.kWorld
    else:
        space = om.MSpace.kObject

    srcShapeDagPath, deleteSrc = _asMesh(srcGeo)
    destShapeDagPath, deleteDest = _asMesh(destGeo)

    try:
        srcMeshFn = om.MFnMesh(srcShapeDagPath)

        #-----------------------|    Cook

        numInfluences = len(weights) // srcMeshFn.numVertices
        srcWeights = np.array(weights,
                              dtype=np.float64).reshape(-1, numInfluences)

        srcPoints = np.array(
            [[p.x, p.y, p.z] for p in srcMeshFn.getPoints(space)],
            dtype=np.float64
        )

        destMeshFn = om.MFnMesh(destShapeDagPath)
        result = np.zeros((destMeshFn.numVertices, numInfluences),
                          dtype=np.float64)
        clampedK = min(k, len(srcPoints))

        for i, pt in enumerate(
                iterPointPositions(destShapeDagPath, worldSpace)
        ):
            closestPt, _ = srcMeshFn.getClosestPoint(pt, space)
            cp = np.array([closestPt.x, closestPt.y, closestPt.z],
                          dtype=np.float64)

            dists = np.linalg.norm(srcPoints - cp, axis=1)
            knnIdx = np.argpartition(dists, clampedK)[:clampedK]
            knnDists = dists[knnIdx]

            eps = 1e-8
            invDists = 1.0 / np.maximum(knnDists, eps)
            invDists /= invDists.sum()

            result[i] = (invDists[:, np.newaxis]
                         * srcWeights[knnIdx]).sum(axis=0)

    finally:
        if deleteSrc:
            om.MGlobal.deleteNode(getParent(srcShapeDagPath).node())
        if deleteDest:
            om.MGlobal.deleteNode(getParent(destShapeDagPath).node())

    return result.ravel().tolist()