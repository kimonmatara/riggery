import re
from typing import Union, Optional, Iterable, Literal
from ..nodetypes import __pool__ as nodes
from ..datatypes import __pool__ as data
from ..plugtypes import __pool__ as plugs
from ..elem import Elem

from riggery.general.iterables import expand_tuples_lists, without_duplicates
import riggery.core.lib.names as _nm
import riggery.core.lib.mixedmode as _mm
SurfaceShape = nodes['SurfaceShape']

from riggery.general.functions import short

import maya.api.OpenMaya as om
import maya.cmds as m


class Mesh(SurfaceShape):

    __point_comp_ext__ = 'vtx'

    #-------------------------------------|    Queries

    def numVertices(self) -> int:
        """:return: The number of vertices on this mesh."""
        return self.__apimfn__().numVertices

    def numFaces(self) -> int:
        """:return: The number of faces on this mesh."""
        return self.__apimfn__().numPolygons

    @short(worldSpace='ws')
    def getClosestPoint(self,
                        point:'data.Point',
                        worldSpace:bool=False) -> tuple['data.Point', int]:
        """
        :return: Tuple of closest point, face ID.
        """
        point, faceId = self.__apimfn__(dag=True).getClosestPoint(
            om.MPoint(point),
            om.MSpace.kWorld if worldSpace else om.MSpace.kObject
        )
        return data['Point'](point), faceId

    # On standby; solution does not have parity with uvPin
    # @short(worldSpace='ws')
    # def getClosestMatrix(self,
    #                      point:'data.Point',
    #                      axis1:Literal['x', 'y', 'z', '-x', '-y', '-z'],
    #                      ref1:Literal['u', 'v', 'n'],
    #                      axis2:Literal['x', 'y', 'z', '-x', '-y', '-z'],
    #                      ref2:Literal['u', 'v', 'n'],
    #                      worldSpace:bool=False,
    #                      uvSet:Optional[str]=None):
    #
    #     meshFn = self.__apimfn__(dag=True)
    #     space = om.MSpace.kWorld if worldSpace else om.MSpace.kObject
    #
    #     if uvSet is None:
    #         uvSet = self.uvSet
    #
    #     point, faceId = meshFn.getClosestPoint(om.MPoint(point), space)
    #     faceVtxIds = meshFn.getPolygonVertices(faceId)
    #
    #     vtxId = min(faceVtxIds,
    #                 key=lambda x: meshFn.getPoint(x, space).distanceTo(point))
    #
    #     refs = {}
    #
    #     if 'u' in (ref1, ref2):
    #         refs['u'] = meshFn.getFaceVertexTangent(faceId, vtxId, space, uvSet)
    #
    #     if 'v' in (ref1, ref2):
    #         refs['v'] = meshFn.getFaceVertexBinormal(faceId, vtxId, space,
    #                                                  uvSet)
    #
    #     if 'n' in (ref1, ref2):
    #         refs['n'] = meshFn.getFaceVertexNormal(faceId, vtxId, space)
    #
    #     return _mm.createOrthoMatrix(axis1, refs[ref1],
    #                                  axis2, refs[ref2],
    #                                  w=point).pick(t=True, r=True)

    #-------------------------------------|    UVs

    def getClosestUV(self,
                     point:'data.Point',
                     worldSpace:bool=False,
                     uvSet:Optional[str]=None) -> tuple[float, float, int]:
        """:return: Tuple of U, V, face ID."""
        point = om.MPoint(point)
        meshFn = self.__apimfn__(dag=True)
        space = om.MSpace.kWorld if worldSpace else om.MSpace.kObject
        closestPoint = meshFn.getClosestPoint(point, space)[0]

        if uvSet is None:
            uvSet = self.uvSet

        return meshFn.getUVAtPoint(closestPoint, space, uvSet)

    def getUVSet(self) -> str:
        """Returns the name of the current UV set."""
        return m.polyUVSet(str(self), q=True, currentUVSet=True)[0]

    getCurrentUVSetName = getUVSet # for parity with PyMEL

    def setUVSet(self, uvSet:str):
        """Sets the current UV set."""
        m.polyUVSet(str(self), e=True, currentUVSet=uvSet)
        return self

    setCurrentUVSetName = setUVSet # for parity with PyMEL

    uvSet = property(getUVSet, setUVSet)

    def getUVSets(self) -> list[str]:
        """:return: The names of the UV sets on this mesh."""
        out = m.polyUVSet(str(self), q=True, allUVSets=1)
        if out:
            return out
        return []

    def createMeshFromUVs(self, scale:float=1.0):
        """Creates a flat mesh from the current UV set."""
        newXf = nodes['Transform'].create()
        newShape = self.duplicate(parent=newXf)[0]
        newXf.rename()

        dag = newShape.__apimdagpath__()

        meshFn  = om.MFnMesh(dag)
        numVerts = meshFn.numVertices

        uvPerVert = [None] * numVerts

        it = om.MItMeshPolygon(dag)

        while not it.isDone():
            verts = it.getVertices()
            uArr, vArr = it.getUVs()

            for localIdx, vertIdx in enumerate(verts):
                if uvPerVert[vertIdx] is None:
                    uvPerVert[vertIdx] = (uArr[localIdx] * scale,
                                          vArr[localIdx] * scale)
            it.next()

        # Build flat point array
        newPts = om.MPointArray()

        for i, uv in enumerate(uvPerVert):
            if uv is None:
                raise RuntimeError(
                    f"Vertex {i} has no UV assignment; check for UV seams"
                )
            u, v = uv

            newPts.append(om.MPoint(u, 0.0, v))

        meshFn.setPoints(newPts, om.MSpace.kObject)
        meshFn.updateSurface()

        m.dgdirty(str(newShape))
        return newShape


    @short(constructionHistory='ch')
    def carpetUVs(self, *components, constructionHistory:Optional[bool]=None):
        """
        Creates grid UVs. Works in the current set.
        """
        if constructionHistory is not None:
            hadHistory = self.hasHistory()

            if hadHistory:
                constructionHistory = True

        if components:
            components = list(
                without_duplicates(expand_tuples_lists(*components))
            )

            if components:
                _components = []

                for x in components:
                    mt = re.match(r"^.*?\.(vtx|f|e|map)\[.*$", x)
                    if mt:
                        typ = mt.group(1)
                    else:
                        raise TypeError("not a mesh component: ", x)
                    if typ != 'f':
                        kw = {'toFace': True}
                        kw[
                            {'vtx': 'fromVertex',
                             'e': 'fromEdge',
                             'map': 'fromUV'}[typ]
                        ] = True
                        _components += m.polyListComponentConversion(x)
                    else:
                        _components.append(x)
                components = _components
        else:
            components = ["{}.f[0:{}]".format(self, self.numFaces()-1)]

        # Auto project
        m.polyAutoProjection(*components,
                             ch=True, lm=0, pb=0, ibd=0, cm=0, l=2,
                             sc=1, o=0, p=12, ps=0.2, ws=True)[0]

        # Unitize
        m.polyForceUV(*components, unitize=True)

        # Move and sew
        m.polyMapSewMove(*components, nf=10, lps=0)

        # Normalize
        m.polyNormalizeUV(*components,
                          normalizeType=1,
                          preserveAspectRatio=False,
                          centerOnTile=False,
                          normalizeDirection=0)

        if constructionHistory is not None:
            if not constructionHistory:
                self.deleteHistory()

        return self

    #-------------------------------------|    Component conversions

    POLYINFO_INDICES_RETURN_PAT = re.compile(r"(?<=\:|[0-9])\s+([0-9]+)")

    def vertsToEdges(self, *vertIndices) -> list[list[int]]:
        """
        :return: A list of lists, where each sub-list comprises the indices for
            the edges connected to the specified vertex.
        """
        _self = str(self)
        vertIndices = expand_tuples_lists(*vertIndices)
        result = m.polyInfo([f"{_self}.vtx[{i}]" for i in vertIndices], ve=True)
        parsed = [
            list(map(int, re.findall(self.POLYINFO_INDICES_RETURN_PAT, x)))
            for x in result
        ]
        return parsed

    def facesToEdges(self, *faceIndices) -> list[list[int]]:
        """
        :return: A list of lists, where each sub-list comprises the indices for
            the edges connected to the specified face.
        """
        _self = str(self)
        faceIndices = expand_tuples_lists(*faceIndices)
        result = m.polyInfo([f"{_self}.f[{i}]" for i in faceIndices], fe=True)
        parsed = [
            list(map(int, re.findall(self.POLYINFO_INDICES_RETURN_PAT, x)))
            for x in result
        ]
        return parsed

    def facesToVerts(self, *faceIndices) -> list[list[int]]:
        """
        :return: A list of lists, where each sub-list comprises the indices for
            the vertices connected to the specified face.
        """
        _self = str(self)
        faceIndices = expand_tuples_lists(*faceIndices)
        result = m.polyInfo([f"{_self}.f[{i}]" for i in faceIndices], fv=True)
        parsed = [
            list(map(int, re.findall(self.POLYINFO_INDICES_RETURN_PAT, x)))
            for x in result
        ]
        return parsed

    def edgesToFaces(self, *edgeIndices) -> list[list[int]]:
        """
        :return: A list of lists, where each sub-list comprises the indices for
            the faces connected to the specified edge.
        """
        _self = str(self)
        result = m.polyInfo([f"{_self}.e[{i}]"
                             for i in expand_tuples_lists(*edgeIndices)],
                            ef=True)
        parsed = [
            list(map(int, re.findall(self.POLYINFO_INDICES_RETURN_PAT, x)))
            for x in result
        ]
        return parsed

    def edgesToVerts(self, *edgeIndices) -> list[list[int]]:
        """
        :return: A list of lists, where each sub-list comprises the indices for
            the vertices connected to the specified edge.
        """
        _self = str(self)
        result = m.polyInfo([f"{_self}.e[{i}]"
                             for i in expand_tuples_lists(*edgeIndices)],
                            ev=True)
        parsed = [
            list(map(int, re.findall(self.POLYINFO_INDICES_RETURN_PAT, x)))
            for x in result
        ]
        return parsed

    POLYINFO_FACE_NORMAL_PAT = re.compile(
        r"^FACE_NORMAL\s+[0-9]+\:\s(.*?)\s(.*?)\s(.*?)\s+$"
    )

    def facesToNormals(self, *faceIndices) -> list['data.Vector']:
        """
        :param \*faceIndices: the indices of the faces to inspect
        :return: The normals for the specified faces, in a list.
        """
        faceIndices = expand_tuples_lists(*faceIndices)
        _self = str(self)

        T = data['Vector']
        result = m.polyInfo([f"{_self}.f[{i}]" for i in faceIndices], fn=True)

        return [T(map(float,
                      re.match(self.POLYINFO_FACE_NORMAL_PAT, x).groups()))
                for x in result]

    #-------------------------------------|    Comparisons

    def similar(self, otherMesh:Union['nodes.DagNode', str]) -> bool:
        """
        Compares meshes for topology.

        :param otherMesh: the mesh against which to compare
        :return: True if the two meshes have the same topology.
        """
        return m.polyCompare(str(self),
                             str(otherMesh),
                             edges=True,
                             faceDesc=True) == 0

    @short(userNormals='un')
    def same(self,
             otherMesh:Union['nodes.DagNode', str],
             userNormals:bool=False) -> bool:
        """
        Compares meshes for topology AND vertex positions.

        :param otherMesh: the mesh against which to compare
        :param userNormals/un: match for user normals too; defaults to False
        :return: True if the two meshes have the same topology and vertex
            positions.
        """
        kw = {'edges': True, 'faceDesc': True, 'vertices': True}

        if userNormals:
            kw['userNormals'] = True

        return m.polyCompare(str(self), str(otherMesh) **kw)

    #-------------------------------------|    Deformation effects

    def flipDelta(self,
                  baseGeo:'nodes.DagNode',
                  axis:Literal['x', 'y', 'z', '-x', '-y', '-z']='x',

                  smoothNormals:Optional[int]=None,
                  smoothInfluences:Optional[int]=None,
                  wrapMode:Optional[Union[int, str]]=None,

                  keepHistory:Optional[bool]=None):
        """
        :param baseGeo: the 'base' (undeformed) version of this shape
        :param axis: the axis along which to flip this shape; defaults to 'x'
        :param keepHistory/kh: ignored if this shape already had history (in
            which case history will always be preserved); defaults to True if
            this shape had history, and False if it didn't
        """
        baseGeo = nodes['DagNode'](baseGeo).toShape()

        hadHistory = self.hasHistory()

        if keepHistory is None:
            keepHistory = hadHistory
        else:
            keepHistory = hadHistory or keepHistory

        thisOrigShape = self.getOrigShape(True)
        baseGeo = baseGeo.duplicate(parent=self.parent,
                                    intermediate=True)[0]
        baseGeo.conformShapeName()

        flipper = data['Matrix']()
        flipper.flipAxis(axis.strip('-'))

        wrap = nodes['ProximityWrap'].createNode().setAttrs(
            **{k: v for k, v in zip(
                ('smoothNormals', 'smoothInfluences', 'wrapMode'),
                (smoothNormals, smoothInfluences, wrapMode)
            ) if v is not None}
        )
        baseGeo.localOutput >> wrap.attr('originalGeometry')[0]

        baseGeo.localOutput >> wrap.attr(
            'input')[0].attr('inputGeometry')

        (baseGeo.localOutput * flipper) >> wrap.attr(
            'drivers')[0].attr('driverBindGeometry')

        (thisOrigShape.localOutput * flipper) >> wrap.attr(
            'drivers')[0].attr('driverGeometry')

        wrap.attr('outputGeometry')[0] >> self.input

        if not keepHistory:
            self.deleteHistory()

        return self

    def copyDeformDelta(
            self,
            startMesh:'nodes.DagNode',
            endMesh:'nodes.DagNode',

            # UV mode
            uvSpace:Optional[bool]=None,
            startUVSet:Optional[str]=None,
            endUVSet:Optional[str]=None,

            # Wrap settings
            smoothNormals:Optional[Union[int, 'plugs.Number']]=None,
            smoothInfluences:Optional[Union[int, 'plugs.Number']]=None,
            globalScale:Optional[
                Union[
                    int,
                    float,
                    'plugs.Number',
                    'data.Matrix',
                    'plugs.Matrix'
                ]
            ]=None
    ) -> dict:
        """
        The rest of the \*\*kwargs concern the final proximity wrap stage.

        :param startMesh: the 'base' mesh for the delta
        :param endMesh: the 'target' mesh for the delta
        :param uvSpace: use this if *startMesh* and *endMesh* have a different
            topology but different UVs; defaults to True if either *startUVSet*
            or *endUVSet* are provided, otherwise False
        :return: A dictionary with these keys: 'transferAttributes' (may be
            omitted), 'proximityWrap'.
        """
        out = {}

        # ingest start mesh / end mesh as shapes
        startShape = nodes['DagNode'](startMesh).toShape()
        startShapeHistoryInput = startShape.getHistoryInput()
        endShape = nodes['DagNode'](endMesh).toShape()

        # resolve space and uv sets
        if uvSpace is None:
            uvSpace = bool(startUVSet or endUVSet)

        if uvSpace:
            if not startUVSet:
                startUVSet = startShape.uvSet

            if not endUVSet:
                endUVSet = endShape.uvSet

        # get our history input and orig shape
        historyInput = self.getHistoryInput(create=True)
        origShape = self.getOrigShape(create=True)

        # resolve start / end orig shapes
        startOrigShape = startShape.getOrigShape()

        if not startOrigShape:
            startOrigShape = startShape

        endOrigShape = endShape.getOrigShape()

        if not endOrigShape:
            endOrigShape = endShape

        if uvSpace:
            transferNode = nodes['TransferAttributes'].createNode(
                transferPositions=True,
                transferNormals=False,
                transferUVs=False,
                transferColors=False,
                sampleSpace=3,
                sourceUVSpace=endUVSet,
                targetUVSpace=startUVSet
            )

            out['transferAttributes'] = transferNode

            startShape.localOutput \
            >> transferNode.attr('input')[0].attr('inputGeometry')

            startOrigShape.localOutput \
            >> transferNode.attr('originalGeometry')[0]

            endShape.localOutput >> transferNode.attr('source')[0]
            morphed = transferNode.attr('outputGeometry')[0]
        else:
            morphed = endShape.localOutput

        # Wrap
        out['proximityWrap'] = wrapNode = nodes['ProximityWrap'].createNode()

        if smoothNormals is not None:
            wrapNode.attr('smoothNormals').put(smoothNormals)

        if smoothInfluences is not None:
            wrapNode.attr('smoothInfluences').put(smoothInfluences)

        if globalScale is not None:
            wrapNode.putGlobalScale(globalScale) # generalized, implement it

        historyInput >> wrapNode.attr('input')[0].attr('inputGeometry')

        origShape.localOutput >> wrapNode.attr('originalGeometry')[0]
        morphed >> wrapNode.attr('drivers')[0].attr('driverGeometry')

        startOrigShape.localOutput \
        >> wrapNode.attr('drivers')[0].attr('driverBindGeometry')

        if startShapeHistoryInput:
            startShapeHistoryInput \
            >> wrapNode.attr('drivers')[0].attr('driverReferenceGeometry')

        # complete the loop
        wrapNode.attr('outputGeometry')[0] >> self.input

        return out