from functools import reduce
from typing import Union, Optional, Literal

import maya.api.OpenMaya as om
import maya.cmds as m

from riggery.general.iterables import expand_tuples_lists
from riggery.general.functions import short, resolve_flags
import riggery.internal.niceunit as _nu
from ..datatypes import __pool__ as data
from ..plugtypes import __pool__ as plugs
from ..nodetypes import __pool__ as nodes
from ..lib import mixedmode as _mm

ROTORDERS = ['xyz', 'yzx', 'zxy', 'xzy', 'yxz', 'zyx']


class Matrix(data['Tensor']):

    __apicls__ = om.MMatrix
    __shape__ = 16

    #-------------------------------------------|    Constructor(s)

    @classmethod
    def createOrtho(cls,
                    aimAxis,
                    aimVector,
                    upAxis,
                    upVector,
                    w=None) -> 'Matrix':
        """
        Creates an orthogonal matrix. Vector magnitudes are not managed.
        Use :meth:`pick` on the output to control for that.

        :param aimAxis: one of 'x', 'y', 'z', '-x', '-y', or '-z'
        :param aimVector: the aim vector
        :param upAxis: one of 'x', 'y', 'z', '-x', '-y', or '-z'
        :param upVector: the up vector
        :param w: an optional translation component
        :return: The matrix.
        """
        swapAim = '-' in aimAxis
        aimAxis = aimAxis.lower().strip('-')

        swapUp = '-' in upAxis
        upAxis = upAxis.lower().strip('-')

        if aimAxis == upAxis:
            raise ValueError("Aim axis same as up axis")

        consec = aimAxis + upAxis in 'xyzxy'

        aimVector = data['Vector'](aimVector)
        upVector = data['Vector'](upVector)

        if swapAim:
            aimVector *= -1.0

        if swapUp:
            upVector *= -1.0

        if consec:
            thirdVector = aimVector ^ upVector
            upVector = thirdVector ^ aimVector
        else:
            thirdVector = upVector ^ aimVector
            upVector = aimVector ^ thirdVector

        thirdAxis = [ax for ax in 'xyz' if ax not in aimAxis+upAxis][0]
        out = Matrix()
        for ax, vector in zip((aimAxis, upAxis, thirdAxis),
                              (aimVector, upVector, thirdVector)):
            setattr(out, ax, vector)

        if w is not None:
            out.w = w

        return out

    #-------------------------------------------|    Testing

    @short(inheritsTransform='it', name='n')
    def loc(self, name=None, /, inheritsTransform:bool=True):
        """
        :param name/n: an optional name for the locator; defaults to block
            naming
        :param inheritsTransform/it: sets the 'inheritsTransform' attribute on
            the locator; defaults to True
        """
        out = nodes.Locator.createNode(name=name).parent
        out.attr('it').set(inheritsTransform)
        m.xform(str(out), matrix=self)
        out.attr('displayLocalAxis').set(True)
        return out

    #-------------------------------------------|    Mult

    def __mul__(self, other):
        other, shape, isPlug = _mm.info(other)
        if shape == 16:
            if isPlug:
                node = nodes.MultMatrix.createNode()
                node.attr('matrixIn')[0].set(self)
                node.attr('matrixIn')[1].put(other, isPlug)
                return node.attr('matrixSum')
            return Matrix(self.api * om.MMatrix(other))
        return NotImplemented

    def __rmul__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 16:
            if isPlug:
                node = nodes.MultMatrix.createNode()
                node.attr('matrixIn')[0].put(other, isPlug)
                node.attr('matrixIn')[1].set(self)
                return node.attr('matrixSum')

            return Matrix(other.api * self.api)

        if shape == 3:
            if isPlug:
                node = nodes.VectorProduct.createNode()
                node.attr('operation').set(3)
                node.attr('input1').put(other, isPlug)
                node.attr('matrix').set(self)
                return node.attr('output')

            return data['Vector'](om.MVector(other) * self.api)

        return NotImplemented

    #-------------------------------------------|    Forced point-matrix mult

    def __rxor__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 3:
            if isPlug:
                node = nodes.PointMatrixMult.createNode()
                node.attr('inMatrix').set(self)
                other.put(other, True)
                return node.attr('output')

            return data['Point'](om.MPoint(other) * self.api)

        return NotImplemented

    #-------------------------------------------|   Row access

    def getAxis(self,
                axis:Literal['x', 'y', 'z', '-x', '-y', '-z', 'w']):
        """
        :return: A vector for the specified axis. Negative axes (e.g. '-y'
            can also be requested).
        """
        out = self.getRow('xyzw'.index(axis.strip('-')))
        if '-' in axis:
            out *= -1.0
        return out

    def _getRowStartEnd(self, rowIndex) -> tuple:
        start = rowIndex * 4
        end = start + 3
        return start, end

    def getRow(self, rowIndex):
        """
        :param rowIndex: the matrix row to retrieve
        :return: The vector or point for the specified row.
        """
        start, end = self._getRowStartEnd(rowIndex)
        return (data['Point'] if rowIndex == 3 \
                    else data['Vector'])(self[start:end])

    def setRow(self, rowIndex, vector):
        """
        :param rowIndex: the row to edit
        :param vector: the vector (or point) to assign to the specified row
        """
        start, end = self._getRowStartEnd(rowIndex)
        self[start: end] = list(vector)

    def getX(self):
        """
        You can also use the ``.x`` property.
        :return: The matrix X axis.
        """
        return self.getRow(0)

    def setX(self, vector):
        """
        You can also use the ``.x`` property.
        :param vector: the vector to assign to the X axis
        """
        self.setRow(0, vector)

    x = property(fget=getX, fset=setX)

    def getY(self):
        """
        You can also use the ``.y`` property.
        :return: The matrix Y axis.
        """
        return self.getRow(1)

    def setY(self, vector):
        """
        You can also use the ``.y`` property.
        :param vector: the vector to assign to the Y axis
        """
        self.setRow(1, vector)

    y = property(fget=getY, fset=setY)

    def getZ(self):
        """
        You can also use the ``.z`` property.
        :return: The matrix Z axis.
        """
        return self.getRow(2)

    def setZ(self, vector):
        """
        You can also use the ``.z`` property.
        :param vector: the vector to assign to the Z axis
        """
        self.setRow(2, vector)

    z = property(fget=getZ, fset=setZ)

    def getW(self):
        """
        :return: The translation component of this matrix.
        """
        out = self.getRow(3)
        return out

    def setW(self, translation):
        """
        :param translation: the point to assign to the translation component
            of this matrix
        """
        self.setRow(3, translation)

    w = property(fget=getW, fset=setW)

    #-------------------------------------------|   Filtering

    def asTranslateMatrix(self) -> 'Matrix':
        """
        :return: A copy of this matrix, pared down to translation.
        """
        out = om.MTransformationMatrix()
        this = om.MTransformationMatrix(self.api)
        translation = this.translation(om.MSpace.kTransform)
        out.setTranslation(translation, om.MSpace.kTransform)
        return Matrix.fromApi(out.asMatrix())

    def asRotateMatrix(self) -> 'Matrix':
        """
        :return: A copy of this matrix, pared down to rotation.
        """
        out = om.MTransformationMatrix()
        this = om.MTransformationMatrix(self.api)
        rotation = this.rotation(om.MSpace.kTransform)
        out.setRotation(rotation)
        return Matrix.fromApi(out.asMatrix())

    def asTranslateRotateMatrix(self):
        return self.asRotateMatrix() * self.asTranslateMatrix()

    def asScaleMatrix(self) -> 'Matrix':
        """
        :return: A copy of this matrix, pared down to scale.
        """
        out = om.MTransformationMatrix()
        this = om.MTransformationMatrix(self.api)
        scale = this.scale(om.MSpace.kTransform)
        out.setScale(scale, om.MSpace.kTransform)
        return Matrix.fromApi(out.asMatrix())

    def asShearMatrix(self) -> 'Matrix':
        """
        :return: A copy of this matrix, pared down to shear.
        """
        out = om.MTransformationMatrix()
        this = om.MTransformationMatrix(self.api)
        shear = this.shear(om.MSpace.kTransform)
        out.setShear(shear, om.MSpace.kTransform)
        return Matrix.fromApi(out.asMatrix())

    @short(translate='t',
           rotate='r',
           scale='s',
           shear='sh')
    def pick(self,
             translate:Optional[bool]=None,
             rotate:Optional[bool]=None,
             scale:Optional[bool]=None,
             shear:Optional[bool]=None, *,
             default:Optional['Matrix']=None) -> 'Matrix':
        """
        Returns a copy of this matrix with translation, rotation, scale and
        shear selectively filtered out.

        The flags are evaluated Maya-style, i.e. if only `translate=True` is
        passed, all the other flags are set to ``False`` etc.

        :param translate: preserve translation
        :param rotate: preserve rotation
        :param scale: preserve scale
        :param shear: preserve shear
        :param default: a fallback matrix from which to derive translation,
            rotation, scale and shear where these are being filtered out;
            defaults to ``None``
        :return: The filtered matrix.
        """
        translate, rotate, scale, shear \
            = resolve_flags(translate, rotate, scale, shear)
        if default:
            default = Matrix(default)

        if all([translate, rotate, scale, shear]):
            return self.copy()

        if not any([translate, rotate, scale, shear]):
            return type(self)()

        matrices = []
        if scale:
            matrices.append(self.asScaleMatrix())
        elif default:
            matrices.append(default.asScaleMatrix())

        if shear:
            matrices.append(self.asShearMatrix())
        elif default:
            matrices.append(default.asShearMatrix())

        if rotate:
            matrices.append(self.asRotateMatrix())
        elif default:
            matrices.append(default.asRotateMatrix())

        if translate:
            matrices.append(self.asTranslateMatrix())
        elif default:
            matrices.append(default.asTranslateMatrix())

        if len(matrices) == 1:
            return matrices[0]

        return reduce(lambda x, y: x * y, matrices)

    #-------------------------------------------|    Decomposition

    @short(rotateOrder='ro')
    def rotation(self, *, asQuaternion=False, rotateOrder=0):
        """
        :param asQuaternion: return a
            :class:`~riggery.core.datatypes.Quaternion` instead of an
            :class:`~riggery.core.datatypes.EulerRotation`; defaults to False
        :param rotateOrder/ro: the rotate order for the euler rotation;
            defaults to 0 ('xyz')
        """
        if asQuaternion:
            return self.quaternion()
        return self.eulerRotation(rotateOrder)

    def eulerRotation(self, order:Union[int, str]=0):
        """
        :param order: the rotation order; defaults to 'xyz'
        :return: The rotation component of this matrix, as an Euler rotation.
        """
        xf = om.MTransformationMatrix(self.api)
        out = xf.rotation(asQuaternion=False)
        rotateOrder = _nu.conformRotateOrder(order)
        if rotateOrder != 0:
            out.reorderIt(rotateOrder)
        return data['EulerRotation'](out)

    def quaternion(self):
        """
        :return: The quaternion for the rotation in this matrix.
        """
        xf = om.MTransformationMatrix(self.api)
        return data['Quaternion'](xf.rotation(asQuaternion=True))

    @short(rotateOrder='ro')
    def decompose(self, rotateOrder:Union[int, str]=0) -> dict:
        """
        :param rotateOrder/ro: the rotate order to use; defaults to 'xyz'
        :return: A dictionary with the following keys: translate, rotate,
            scasle, shear, rotateOrder
        """
        rotateOrder = _nu.conformRotateOrder(rotateOrder)
        out = {}
        xf = om.MTransformationMatrix(self.api)
        out['shear'] = data['Vector'](xf.shear(om.MSpace.kTransform))
        out['scale'] = data['Vector'](xf.scale(om.MSpace.kTransform))

        rotation = xf.rotation(asQuaternion=False)
        if rotateOrder != 0:
            rotation.reorderIt(rotateOrder)
        out['rotate'] = data['EulerRotation'](rotation)
        out['translate'] = data['Point'](xf.translation(om.MSpace.kTransform))
        out['rotateOrder'] = rotateOrder

        return out

    def _decomposeAndApply(
            self,
            transform,
            translate=True,
            rotate=True,
            scale=True,
            shear=True,
            compensatePivots=False,
            compensateJointOrient=True,
            compensateRotateAxis=False,
            compensateJointScale=True,
            worldSpace=False
    ):
        #-------------------------------------|    Prep

        xf = nodes['Transform'](transform)
        isJoint = xf.nodeType() == 'joint'

        if isJoint:
            compensatePivots = False
            fast = not any([compensateRotateAxis,
                compensateJointScale, compensateJointOrient])
        else:
            compensateJointScale = compensateJointOrient = False
            fast = not any([compensateRotateAxis, compensatePivots])

        #-------------------------------------|    Preprocessing

        matrix = self

        if worldSpace:
            matrix *= xf.attr('pim')[0].get()

        #-------------------------------------|    Fast bail

        if fast:
            decomposition = matrix.decompose(
                ro=xf.attr('ro').get(asString=True))

            for channel, state in zip(
                ['translate', 'rotate', 'scale', 'shear'],
                [translate, rotate, scale, shear]
            ):
                dest = xf.attr(channel)
                if state:
                    try:
                        dest.set(decomposition[channel])
                    except:
                        m.warning("couldn't set {}".format(dest))
            return self

        #-------------------------|    Disassemble

        tmtx = matrix.pick(translate=True)

        if compensateJointScale and xf.attr('segmentScaleCompensate').get():
            pismtx = xf.attr('inverseScale').get().asScaleMatrix()
            matrix *= pismtx

        smtx = matrix.pick(scale=True, shear=True)
        rmtx = matrix.pick(rotate=True)

        #-------------------------|    Rotation compensations

        if compensateRotateAxis:
            ramtx = xf.attr('rotateAxis').get().asMatrix()
            rmtx = ramtx.inverse() * rmtx

        if compensateJointOrient:
            jomtx = xf.attr('jointOrient').get().asMatrix()
            rmtx *= jomtx.inverse()

        #-------------------------|    Pivot compensations

        if compensatePivots and not isJoint:
            # Solve as Maya would

            ramtx = xf.getRotateAxisMatrix()
            spmtx = xf.attr('scalePivot').get().asTranslateMatrix()
            stmtx = xf.attr('scalePivotTranslate').get().asTranslateMatrix()
            rpmtx = xf.attr('rotatePivot').get().asTranslateMatrix()
            rtmtx = xf.attr('rotatePivotTranslate').get().asTranslateMatrix()

            partialMatrix = spmtx.inverse() * smtx * spmtx * stmtx * \
                            rpmtx.inverse() * ramtx * rmtx * rpmtx * rtmtx

            # Capture and negate translation contribution
            translateContribution = partialMatrix.pick(translate=True)
            tmtx *= translateContribution.inverse()

        #-------------------------|    Reassemble & apply

        matrix = smtx * rmtx * tmtx
        decomposition = matrix.decompose(ro=xf.attr('ro').get(asString=True))

        for channel, state in zip(
                ('translate', 'rotate', 'scale', 'shear'),
                (translate, rotate, scale, shear)
        ):
            if state:
                source = decomposition[channel]
                dest = xf.attr(channel)
                try:
                    dest.set(source)
                except:
                    m.warning("couldn't set {}".format(dest))
        return self

    @short(
        translate='t',
        rotate='r',
        scale='s',
        shear='sh',
        compensatePivots='cp',
        compensateJointOrient='cjo',
        compensateRotateAxis='cra',
        compensateJointScale='cjs',
        worldSpace='ws',
        maintainOffset='mo'
    )
    def decomposeAndApply(
            self,
            *slaves,
            translate=None,
            rotate=None,
            scale=None,
            shear=None,
            compensatePivots=False,
            compensateJointOrient=True,
            compensateRotateAxis=False,
            compensateJointScale=True,
            worldSpace=False,
            maintainOffset=False
    ):
        _Transform = nodes['Transform']
        slaves = [_Transform(slave) for slave in expand_tuples_lists(*slaves)]

        if not slaves:
            raise ValueError("No slaves specified.")

        if maintainOffset:
            m.warning("soft matrix with maintain offset; skipping")
            return

        translate, rotate, scale, shear = resolve_flags(
            translate, rotate, scale, shear
        )

        if not any([translate, rotate, scale, shear]):
            m.warning("no channels requested")
            return self

        for slave in slaves:
            self._decomposeAndApply(slave,
                                    translate=translate,
                                    rotate=rotate,
                                    scale=scale,
                                    shear=shear,
                                    worldSpace=worldSpace,
                                    compensatePivots=compensatePivots,
                                    compensateJointOrient=compensateJointOrient,
                                    compensateRotateAxis=compensateRotateAxis,
                                    compensateJointScale=compensateJointScale)

    #-------------------------------------------|   Misc operations

    def inverse(self) -> 'Matrix':
        """
        :return: The inverse of this matrix.
        """
        return type(self).fromApi(self.api.inverse())

    @short(weight='w')
    def blend(self, matrixPlug, weight=0.5):
        """
        Only supported when blending towards a plug.

        :param matrixPlug: the matrix plug towards which to blend
        :param weight/w: the blending weight, defaults to 0.5
        :return: The blended matrix attribute output.
        """
        otherMatrix, _, otherIsPlug = _mm.info(matrixPlug, plugs['Matrix'])
        if not otherIsPlug:
            raise TypeError("only supported for matrix plug")
        node = nodes['BlendMatrix'].createNode()
        node.attr('inputMatrix').set(self)
        otherMatrix >> node.attr('target')[0].attr('targetMatrix')
        weight >> node.attr('target')[0].attr('weight')

        return node.attr('outputMatrix')

    def normalizeAxes(self):
        """
        In-place operation. Normalizes the axis vectors on this matrix.
        :return: Self.
        """
        for ax in 'xyz':
            setattr(self, ax, getattr(self, ax).normal())
        return self

    def withNormalizedAxes(self) -> 'Matrix':
        """
        :return: A copy of this matrix with the basis vectors normalized.
        """
        return self.copy().normalizeAxes()

    @short(includeNegative='ing')
    def closestAxis(self,
                    refVector,
                    includeNegative:bool=False,
                    asString:bool=False):
        """
        :param refVector: the vector to compare to
        :param includeNegative: including negative axes (e.g. '-x') in the
            calculation
        :param asString: return 'x' instead of [1, 0, 0], etc.
        """
        refVector = data['Vector'](refVector).normal()

        testVecs = {'xyz'[i]: self.getRow(i) for i in range(3)}
        if includeNegative:
            testVecs.update({'-'+('xyz'[i]): -self.getRow(i) \
                             for i in range(3)})
        bestDot = None
        bestVector = None
        bestAxis = None

        for axis, vec in testVecs.items():
            dot = vec.normal().dot(refVector)
            if bestDot is None or dot > bestDot:
                bestDot = dot
                bestVector = vec
                bestAxis = axis

        if asString:
            return bestAxis
        return bestVector

    def averageScale(self) -> float:
        """
        :return: The average of the base axes' magnitudes.
        """
        return sum([self.x.length(),
                    self.y.length(),
                    self.z.length()]) / 3.0

    def asOffset(self):
        """
        This is here for parity with the plug counterpart. It just returns an
        identity matrix.
        """
        return Matrix()

    def asPlug(self):
        """
        Creates a ``holdMatrix`` node, sets its input to this matrix, and
        returns the output.
        """
        node = nodes['HoldMatrix'].createNode()
        node.attr('inMatrix').set(self)
        return node.attr('outMatrix')

    def isOrtho(self) -> bool:
        """
        :return: True if this matrix is orthogonal.
        """
        x = self.x
        y = self.y
        z = self.z.normal()
        cross = x.cross(y).normal()
        dot = cross.dot(z.normal())
        return dot > 1-1e-7

    def isFlipped(self) -> bool:
        """
        :return: True if this matrix is flipped / mirrored.
        """
        return self.api.det3x3() < 0

    def flipAxis(self, axis:str):
        """
        In-place operation. Flips the vector for the specified axis.

        :param axis: the axis to flip (e.g. 'x')
        :return: Self.
        """
        axis = axis.strip('-')
        setattr(self, axis, -getattr(self, axis))
        return self