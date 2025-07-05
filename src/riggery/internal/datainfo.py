from functools import cache
from .typeutil import TypeTree

DATA_TREE = TypeTree.from_text(
    """
    Data
        Unit
            Distance
            Angle
            Time
        Tensor
            Tensor2
                Vector2
                    Point2
            Tensor3
                Vector
                    Point
                EulerRotation
            Tensor4
                Quaternion
                Point4
            BoundingBox
            Matrix
    """
)

@cache
def getPathFromKey(key:str) -> list[str]:
    """
    Given an abstract plug class name, returns an inverse MRO.
    """
    return DATA_TREE.get_path_to(key)