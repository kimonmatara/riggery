from typing import Optional
import maya.api.OpenMaya as om

def toShape(dagPath:om.MDagPath, ranked:bool=False) -> Optional[om.MDagPath]:
    """
    :param dagPath: the DAG path to a shape or transform; if it's a shape, it
        will be returned as-is; otherwise, a shape will be chased
    :param ranked: prioritize non-intermediate shapes; defaults to True
    :return: The DAG path to the shape, or None if no shape could be detected.
    """
    node = dagPath.node()

    if node.hasFn(om.MFn.kShape):
        return dagPath

    if node.hasFn(om.MFn.kTransform):
        if ranked:
            shapes = []

            for i in range(dagPath.numberOfShapesDirectlyBelow()):
                child = om.MDagPath(dagPath)
                child.extendToShape(i)
                shapes.append(child)

            if shapes:
                nonInterm = (x for x in shapes
                             if not om.MFnDagNode(x).isIntermediateObject)

                return next(nonInterm, next(iter(shapes)))
        else:
            out = dagPath.extendToShape()

            if out.isValid():
                return out

def getParent(dagPath:om.MDagPath) -> Optional[om.MDagPath]:
    """:return: The parent dag path, if any, otherwise None."""
    dagPath = om.MDagPath(dagPath)
    dagPath.pop()

    if dagPath.isValid():
        return dagPath

def setParent(child:om.MDagPath, parent:Optional[om.MDagPath]) -> None:
    """
    This does NOT preserve world pose.
    """
    currentParent = getParent(child)

    if currentParent == parent:
        return child

    mod = om.MDagModifier()

    if parent is None:
        parentMo = om.MObject.kNullObj
    else:
        parentMo = parent.node()

    childMo = child.node()
    mod.reparentNode(childMo, parentMo)
    mod.doIt()