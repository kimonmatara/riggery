from typing import Optional, Union, Literal

from ..nodetypes import __pool__ as nodes
from riggery.general.functions import short
from ..lib import names as _n

import maya.api.OpenMaya as om
import maya.cmds as m


class Shape(nodes['DagNode']):

    #------------------------------|    Constructor(s)

    @classmethod
    @short(name='n', parent='p')
    def createNode(cls, *, name:Optional[str]=None, parent=None):
        """
        Creates a shape node of this type.

        :param name/n: if omitted, uses name blocks
        :param parent/p: an optional destination parent for the node
        :return: The node.
        """
        return super()._createAsShape(name=name, parent=parent)

    def assignDefaultShader(self):
        """
        Assigns the default shader (typically ``lambert1``) to this shape.

        :return: self
        """
        pass

    #------------------------------|    DAG

    def isShape(self) -> Literal[True]:
        """
        On :class:`Shape` this always returns True.
        """
        return True

    def toShape(self):
        """
        On :class:`Shape` this always returns self.
        """
        return self

    def toTransform(self):
        """
        :return: This shape's parent.
        """
        return self.parent

    def getParent(self, index=1):
        return super().getParent(index)

    @short(addObject='add')
    def setParent(self, newParent, /, addObject=False, **_):
        """
        Sets this transform's parent.

        :param newParent: the parent; unlike with transforms, this cannot be
            ``None``
        :param relative/r: ignored on shapes; reparenting is always relative
        :param addObject/add: create an instance of this shape rather than
            reparenting
        :return: Either ``self`` or, if *addObject* was requested, a new
            instance.
        """
        if newParent is None:
            raise ValueError("Shapes cannot be parented to the world")

        newParent = nodes['Transform'](newParent)

        if self.parent == newParent:
            if addObject:
                raise ValueError(
                    "Can't create shape instances under same parent"
                )
            return self

        args = [str(self), str(newParent)]
        kwargs = {'shape': True, 'relative': True}
        if addObject:
            kwargs['addObject'] = True
        result = m.parent(*args, **kwargs)[0]
        if addObject:
            return Shape(result)
        return self

    parent = property(getParent, setParent)

    def removeInstance(self) -> None:
        m.parent(str(self), removeObject=True, shape=True)

    @short(name='n')
    def duplicate(self, *, name:Optional[str]=None) -> list:
        """
        .. warning::

            This is not implemented the same as in Maya / PyMEL; the shape
            is strictly duplicated under its existing parent.

        :param name/n: an optional name for the copy; if omitted, defaults to
            standard shape naming
        :return: The duplicate, in a list, per PyMEL / Maya convention.
        """
        px1 = nodes['Transform'].createNode()
        self.setParent(px1, add=True)
        px2 = px1.duplicate()[0]
        m.delete(str(px1))
        shape = px2.shape
        shape.parent = self.parent
        m.delete(str(px2))

        if name is None:
            shape.conformShapeName()
        else:
            shape.name = name
        return [shape]

    #------------------------------|    Conform shape name

    @property
    def defaultTypeSuffix(self):
        return None

    def conformShapeName(self) -> str:
        """
        Renames this shape per Maya conventions.

        :return: The conformed name.
        """
        template, num = self.parent.getShapeNameTemplate()
        existingNames = set([sibling.absoluteName() \
                             for sibling in self.siblings])

        while True:
            newName = template.format(num if num else '')
            if newName in existingNames:
                num += 1
                continue
            self.name = newName
            return newName