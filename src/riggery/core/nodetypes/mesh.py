import re
from typing import Union, Optional, Iterable
from ..nodetypes import __pool__ as nodes
from ..datatypes import __pool__ as data

from riggery.general.iterables import expand_tuples_lists
SurfaceShape = nodes['SurfaceShape']

from riggery.general.functions import short

import maya.cmds as m


class Mesh(SurfaceShape):

    #-------------------------------------|    Queries

    def numVertices(self) -> int:
        """:return: The number of vertices on this mesh."""
        return self.__apimfn__().numVertices

    #-------------------------------------|    UV set get / set

    def getUVSet(self) -> str:
        """Returns the name of the current UV set."""
        return m.polyUVSet(str(self), q=True, currentUVSet=True)

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

    #-------------------------------------|    Component conversions

    POLYINFO_INDICES_RETURN_PAT = re.compile(r"(?<=\:|[0-9])\s+([0-9]+)")
    
    def vertsToEdges(self, *vertIndices) -> list[list[int]]:
        """q
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