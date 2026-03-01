from typing import Union, Optional
import maya.api.OpenMaya as om


def _conformIndexToUV(
        index:Union[int, tuple[int, int]],
        numInV:int
) -> tuple[int, int]:
    if (isinstance(index, tuple)
            and len(index) == 2
            and all((isinstance(x, int) for x in index))):
        return index

    if isinstance(index, int):
        return index // numInV, index % numInV

    raise TypeError("expected int or tuple of two ints")

def _conformIndexToUVW(
        index:Union[int, tuple[int, int, int]],
        numInV:int,
        numInW:int,
) -> tuple[int, int, int]:
    if (isinstance(index, tuple)
            and len(index) == 3
            and all((isinstance(x, int) for x in index))):
        return index

    if isinstance(index, int):
        u = index // (numInV * numInW)
        remainder = index % (numInV * numInW)
        v = remainder // numInW
        w = remainder % numInW
        return u, v, w

    raise TypeError("expected int or tuple of three ints")

def getCompMObjectFromIndices(shape:Union[om.MObject, om.MDagPath],
                              index:Optional[
                                  Union[
                                      int,
                                      list[int],
                                      tuple[int, int],
                                      list[tuple[int, int]],
                                      tuple[int, int, int],
                                      list[tuple[int, int, int]],
                                  ]
                              ]=None) -> om.MObject:
    """
    :param shape: the MObject for a mesh, NURBS curve or NURBS surface shape
    :param index: where tuples are encountered, they will be interpreted as
        (u, v) or (u, v, w) indices. Where integers are encountered, they will
        be interpreted as 'flat' indices, even for multi-indexed components.
    :return: The component MObject.
    """
    if isinstance(shape, om.MDagPath):
        shape = shape.node()

    if index is None:
        indices = None
    else:
        if isinstance(index, tuple):
            indices = [index]
        else:
            try:
                indices = list(index)
            except TypeError:
                indices = [index]

    if shape.hasFn(om.MFn.kMesh):
        compFn = om.MFnSingleIndexedComponent()
        comp = compFn.create(om.MFn.kMeshVertComponent)

        if indices is None:
            count = om.MFnMesh(shape).numVertices
            compFn.setCompleteData(count)
        else:
            compFn.addElements(indices)

    elif shape.hasFn(om.MFn.kNurbsCurve):
        compFn = om.MFnSingleIndexedComponent()
        comp = compFn.create(om.MFn.kCurveCVComponent)

        if indices is None:
            count = om.MFnNurbsCurve(shape).numCVs
            compFn.setCompleteData(count)
        else:
            compFn.addElements(indices)

    elif shape.hasFn(om.MFn.kNurbsSurface):
        compFn = om.MFnDoubleIndexedComponent()
        comp = compFn.create(om.MFn.kSurfaceCVComponent)

        srfFn = om.MFnNurbsSurface(shape)

        if indices is None:
            compFn.setCompleteData(srfFn.numCVsInU, srfFn.numCVsInV)
        else:
            numCVsInV = srfFn.numCVsInV
            uvPairs = [_conformIndexToUV(index, numCVsInV) for index in indices]
            compFn.addElements(uvPairs)

    elif shape.hasFn(om.MFn.kLattice):
        compFn = om.MFnTripleIndexedComponent()
        comp = compFn.create(om.MFn.kLatticeComponent)

        shapeFn = om.MFnDependencyNode(shape)

        if indices is None:
            numS = shapeFn.findPlug("sDivisions", False).asInt()
            numT = shapeFn.findPlug("tDivisions", False).asInt()
            numU = shapeFn.findPlug("uDivisions", False).asInt()

            compFn.setCompleteData(numS, numT, numU)
        else:
            numT = shapeFn.findPlug("tDivisions", False).asInt()
            numU = shapeFn.findPlug("uDivisions", False).asInt()

            uvTriples = [_conformIndexToUVW(index, numT, numU)
                         for index in indices]
            compFn.addElements(uvTriples)
    else:
        raise TypeError("Unsupported geometry type: '{}'".format(
            shape.apiTypeStr)
        )

    return comp