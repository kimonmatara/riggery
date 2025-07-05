import maya.cmds as m

from ..nodetypes import __pool__


class FourByFourMatrix(__pool__['DependNode']):

    def set(self, matrix):
        """
        :param matrix: the matrix to set this node's fields to
        """
        matrix = list(matrix)

        for i, axis in enumerate('xyzw'):
            valStart = i * 4
            valEnd = valStart + 4

            compoundName = f'{axis}Row'
            if self.hasAttr(compoundName):
                fields = self.attr(compoundName).getChildren()
            else:
                fieldStart = i * 10
                fieldEnd = fieldStart + 4
                fields = [self.attr('in{}'.format(str(i).zfill(2))
                                    ) for i in range(fieldStart, fieldEnd)]

            values = matrix[valStart:valEnd]
            for field, value in zip(fields, values):
                field.set(value)
        return self

    @property
    def x(self):
        """
        Auto-configures a compound proxy for the X-axis row of the matrix.
        """
        return self._initAxisCompound('x')

    @property
    def y(self):
        """
        Auto-configures a compound proxy for the Y-axis row of the matrix.
        """
        return self._initAxisCompound('y')

    @property
    def z(self):
        """
        Auto-configures a compound proxy for the Z-axis row of the matrix.
        """
        return self._initAxisCompound('z')

    @property
    def w(self):
        """
        Auto-configures a compound proxy for the translation row of the
        matrix.
        """
        return self._initAxisCompound('w')

    def _initAxisCompound(self, axis:str):
        attrName = f"{axis}Row"
        try:
            return self.attr(attrName)
        except AttributeError:
            rowIndex = 'xyzw'.index(axis)
            _self = str(self)
            m.addAttr(_self,
                      ln=attrName,
                      at='double3',
                      nc=3)
            asPoint = axis == 'w'
            for ax in 'XYZ':
                m.addAttr(_self,
                          ln=f"{attrName}{ax}",
                          k=True,
                          at='doubleLinear' if asPoint else 'double',
                          parent=attrName)

            attr = self.attr(attrName)
            start = rowIndex * 10
            end = start + 3
            stdFields = [self.attr('in{}'.format(
                str(i).zfill(2))) for i in range(start, end)]

            for virtualField, stdField in zip(
                attr.getChildren(),
                stdFields
            ):
                virtualField.set(stdField.get())
                virtualField >> stdField

            endFieldName = 'in{}'.format(str(end).zfill(2))
            endField = self.attr(endFieldName)
            endField.set(1.0 if rowIndex == 3 else 0.0)
            endField.lock()

            return attr