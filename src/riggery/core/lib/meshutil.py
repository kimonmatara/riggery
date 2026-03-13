from itertools import chain
from typing import Literal, Iterator
import re

from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists, without_duplicates
import maya.cmds as m
import maya.api.OpenMaya as om

from ..nodetypes import __pool__ as nodes
from ..datatypes import __pool__ as data

SUPPORTED_CAST_TYPES = {'vtx', 'e', 'f', 'map'}
MESH_COMP_CAST_PAT = re.compile(r"^.*?\.(vtx|e|f|uv)\[.*?\]$")

@short(expandMeshes='em', flatten='fl')
def castComponent(
        component:str,
        preferredType:Literal[tuple(SUPPORTED_CAST_TYPES)],
        flatten:bool=False,
        expandMeshes:bool=False
) -> list[str]:
    """
    Expects a single component string (which could be a range), but always
    returns a list.

    :param component: the component to inspect / cast
    :param preferredType: the type to cast to; one of 'f', 'vtx', 'e', or 'map'
    :param flatten/fl: flatten any component ranges in the return list; defaults
        to False
    :param expandMeshes/em: if a mesh is passed-in instead of a component,
        return a full component instead of throwing :class:`TypeError`; defaults
        to False
    """
    if preferredType not in SUPPORTED_CAST_TYPES:
        raise ValueError(
            "expected 'vtx', 'e', 'f' or 'map': {}".format(preferredType)
        )

    mt = re.match(MESH_COMP_CAST_PAT, component)

    if mt:
        thisType = mt.group(1)

        if thisType in SUPPORTED_CAST_TYPES:
            if thisType == preferredType:
                return [component]

            kwargs = {{'vtx': 'fromVertex',
                       'e': 'fromEdge',
                       'f': 'fromFace',
                       'map': 'fromUV',
                       }[thisType]: True,
                      {'vtx': 'toVertex',
                       'e': 'toEdge',
                       'f': 'toFace',
                       'map': 'toUV',
                       }[preferredType]: True}

            out = m.polyListComponentConversion(component, **kwargs)

            if flatten:
                out = m.ls(out, flatten=True)

            return out
        else:
            raise TypeError(
                "Not a mesh vertex, edge, face, UV or mesh: ", component
            )
    else:
        if expandMeshes:
            try:
                e = nodes['DagNode'](component)
            except:
                raise TypeError(
                    "Not a mesh vertex, edge, face, UV or mesh: ", component
                )

            try:
                e = e.toShape()
            except AttributeError:
                raise TypeError(
                    "Not a mesh vertex, edge, face, UV or mesh: ", component
                )

            if isinstance(e, nodes['Mesh']):
                item = f"{e}.{preferredType}[*]"
                if flatten:
                    out = m.ls(item, flatten=True)
                else:
                    out = [item]

                return out

            raise TypeError(
                "Not a mesh vertex, edge, face, UV or mesh: ", component
            )
        else:
            raise TypeError("Not a mesh vertex, edge, face or UV: ", component)

@short(removeDuplicates='rd',
       flatten='fl',
       expandMeshes='em')
def castComponents(components:list[str],
                   preferredType:Literal['vtx', 'e', 'f', 'map'],
                   flatten:bool=False,
                   removeDuplicates:bool=False,
                   expandMeshes:bool=False
                   ) -> list[str]:
    """
    Conforms a list of mesh components into a preferred type.

    :param components: a list[str] of mesh faces, edges, vertices or UVs
    :param preferredType: the type to convert / expand to; one of 'vtx', 'e',
        'f' or 'map' (for UVs)
    :param flatten/fl: flatten the component list; defaults to False
    :param removeDuplicates/rd: remove duplicates in the return list; defaults
        to False
    :param expandMeshes/em: if a mesh is passed-in instead of a component,
        return a full component instead of throwing :class:`TypeError`; defaults
        to False
    """
    out = list(
        chain.from_iterable(
            (castComponent(x,
                           preferredType,
                           expandMeshes=expandMeshes) for x in components)
        )
    )

    if flatten:
        out = m.ls(out, flatten=True)

    if removeDuplicates:
        out = list(without_duplicates(out))

    return out

def getMeshFn(mesh:str) -> om.MFnMesh:
    """
    :param mesh: the mesh shape or transform, as a string
    """
    sel = om.MSelectionList()
    sel.add(mesh)
    dagPath = sel.getDagPath(0)
    dagPath.extendToShape()
    return om.MFnMesh(dagPath)

def selectVertsByRaycastFromMesh(carrierMesh:str,
                                 selectorMesh:str) -> Iterator[int]:
    """
    Yields indices of vertices on *carrierMesh* that are hit by rays cast from
    faces on *selectorMesh*.

    This is strict, not bidirectional.
    """
    # Get Fns
    fnCarrier = getMeshFn(carrierMesh)
    fnSelector = getMeshFn(selectorMesh)

    # Precompute normals for every face on selectorMesh; store them
    numSelectorFaces = fnSelector.numPolygons
    allSelectorNormals = [fnSelector.getPolygonNormal(i,
                                                      om.MSpace.kWorld).normal()
                          for i in range(numSelectorFaces)]

    for carrierVertexIndex in range(fnCarrier.numVertices):
        carrierVertexPoint = fnCarrier.getPoint(carrierVertexIndex,
                                                om.MSpace.kWorld)
        rayOrigin = om.MFloatPoint(carrierVertexPoint)

        carrierVertexNormal = fnCarrier.getVertexNormal(
            carrierVertexIndex,
            True,
            om.MSpace.kWorld
        ).normal()

        for selectorFaceIndex in range(numSelectorFaces):
            selectorFaceNormal = allSelectorNormals[selectorFaceIndex]

            if selectorFaceNormal * carrierVertexNormal > 0:
                continue

            rayDirection = om.MFloatVector(-selectorFaceNormal)

            if fnSelector.anyIntersection(rayOrigin,
                                          rayDirection,
                                          om.MSpace.kWorld,
                                          999999,
                                          False):
                yield carrierVertexIndex
                break

def selectVertsInsideMesh(carrierMesh: str,
                          selectorMesh: str) -> Iterator[int]:
    """
    Yields the indices of vertices on *carrierMesh* contained by *selectorMesh*.

    :param carrierMesh: the mesh on which to select vertices
    :param selectorMesh: the 'container' mesh; this must be closed
    """
    fnCarrier = getMeshFn(carrierMesh)
    fnSelector = getMeshFn(selectorMesh)

    carrierPts = fnCarrier.getPoints(om.MSpace.kWorld)
    rayDir = om.MFloatVector(0, 1, 0)
    result = []

    for i, pt in enumerate(carrierPts):
        raySrc = om.MFloatPoint(pt.x, pt.y, pt.z)
        hits = fnSelector.allIntersections(raySrc,
                                           rayDir,
                                           om.MSpace.kWorld, 999999, False)
        if hits is not None and len(hits[0]) % 2 == 1:
            yield i

def selectVertsInsideCylinder(carrierMesh:str,
                              cylinderBase:om.MPoint,
                              cylinderVector:om.MVector,
                              cylinderRadius:float) -> Iterator[int]:
    fnCarrier = getMeshFn(carrierMesh)

    axisLength = cylinderVector.length()
    axisDir = cylinderVector.normal()
    radiusSq = cylinderRadius ** 2

    for vertIdx in range(fnCarrier.numVertices):
        pt = fnCarrier.getPoint(vertIdx, om.MSpace.kWorld)
        toVert = om.MVector(pt - cylinderBase)

        projection = toVert * axisDir

        if projection < 0 or projection > axisLength:
            continue

        radialDistSq = (toVert - axisDir * projection).length() ** 2

        if radialDistSq <= radiusSq:
            yield vertIdx

def selectVertsInsideCylinder(carrierMesh:str,
                              cylinderBase:om.MPoint,
                              cylinderVector:om.MVector,
                              cylinderRadius:float,
                              firstHit:bool=False) -> Iterator[int]:
    """
    Yields indices of vertices on *carrierMesh* that fall inside a cylinder
    defined by a base point, an axis vector (whose magnitude defines the
    cylinder length), and a radius.

    :param carrierMesh: shape node, as a string
    :param cylinderBase: base center point of the cylinder
    :param cylinderVector: axis vector; direction and magnitude define the
        cylinder's orientation and length
    :param cylinderRadius: radius of the cylinder
    :param firstHit: if True, discards vertices that are occluded from the
        cylinder axis by the carrier mesh itself
    """
    fnCarrier = getMeshFn(carrierMesh)

    axisLength = cylinderVector.length()
    axisDir = cylinderVector.normal()
    radiusSq = cylinderRadius ** 2

    for vertIdx in range(fnCarrier.numVertices):
        pt = fnCarrier.getPoint(vertIdx, om.MSpace.kWorld)
        toVert = om.MVector(pt - cylinderBase)

        projection = toVert * axisDir

        if projection < 0 or projection > axisLength:
            continue

        radialVec = toVert - axisDir * projection
        if radialVec.length() ** 2 > radiusSq:
            continue

        if firstHit:
            axisPoint = om.MPoint(cylinderBase + axisDir * projection)
            toAxis = om.MVector(axisPoint - pt).normal()
            toAxisF = om.MFloatVector(toAxis.x, toAxis.y, toAxis.z)
            raySrc = om.MFloatPoint(pt)

            offset = 1e-4
            offsetSrc = om.MFloatPoint(pt.x + toAxisF.x * offset,
                                       pt.y + toAxisF.y * offset,
                                       pt.z + toAxisF.z * offset)

            carrierHit = fnCarrier.closestIntersection(offsetSrc,
                                                       toAxisF,
                                                       om.MSpace.kWorld,
                                                       radialVec.length(),
                                                       False)
            if carrierHit is not None:
                continue

        yield vertIdx