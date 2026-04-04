import maya.api.OpenMaya as om

def setMatrix(transformNode:om.MDagPath,
              matrix:om.MMatrix,
              worldSpace:bool=False):
    if worldSpace:
        matrix = matrix * transformNode.exclusiveMatrixInverse()
    xfFn = om.MFnTransform(transformNode)
    xfFn.setTransformation(om.MTransformationMatrix(matrix))

def getMatrix(transformNode:om.MDagPath, worldSpace:bool=False) -> om.MMatrix:
    xfFn = om.MFnTransform(transformNode)
    matrix = xfFn.transformation().asMatrix()

    if worldSpace:
        matrix = matrix * transformNode.exclusiveMatrix()

    return matrix