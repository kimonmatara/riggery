from functools import cached_property, reduce
from typing import Union, Optional, Literal

from riggery.core.lib.evaluation import cache_dg_output
from riggery.general.functions import short, resolve_flags
from riggery.general.iterables import expand_tuples_lists
import riggery.internal.mfnmatches as _mfm
from ..lib import names as _nm
from ..plugtypes import __pool__ as plugs
from ..datatypes import __pool__ as data
from ..nodetypes import __pool__ as nodes
from ..lib import mixedmode as _mm, \
    names as _nm

import maya.api.OpenMaya as om
import maya.cmds as m

def collapseFactors(factors:list):
    num = len(factors)
    if num == 0:
        return None
    if num == 1:
        return factors[0]
    return reduce(lambda x, y: x * y, factors)


class Matrix(plugs['Tensor']):

    __datacls__ = data['Matrix']
    __shape__ = 16

    #-----------------------------------------|    Testing

    @short(inheritsTransform='it',
           translate='t',
           rotate='r',
           scale='s',
           shear='sh',
           parent='p',
           displayType='dt',
           decompose='dec')
    def loc(self,
            name:Optional[str]=None, *,
            inheritsTransform:bool=True,
            displayType=None,
            localScale=None,
            parent=None,
            translate=None,
            rotate=None,
            scale=None,
            shear=None,
            decompose:bool=False):
        """
        Creates a locator and drives it using this matrix.

        :param name: an optional name; defaults to block naming
        :param inheritsTransform/it: sets the 'inheritsTransform' attribute on
            the locator; defaults to True
        """
        locShape = nodes.Locator.createNode(name=name)

        if localScale is not None:
            locShape.attr('localScale').set(localScale)

        if displayType is not None:
            locShape.attr('overrideEnabled').set(True)
            locShape.attr('overrideDisplayType').set(displayType)

        loc = locShape.parent
        loc.attr('displayLocalAxis').set(True)
        loc.attr('it').set(inheritsTransform)

        if parent is not None:
            loc.setParent(parent, relative=True)

        matrix = self.pick(translate=translate,
                           rotate=rotate,
                           scale=scale,
                           shear=shear)

        if decompose:
            matrix.decomposeAndApply(loc)
        else:
            matrix.applyViaOpm(loc)
            loc.maskAnimAttrs(cb=['v'])

        return loc

    #-----------------------------------------|    API

    def __apimfntype__(self):
        mobj = self.__apiobjects__.setdefault(
            'MObject',
            self.__apiobjects__['MPlug'].attribute()
        )

        if mobj.hasFn(om.MFn.kMatrixAttribute):
            return om.MFnMatrixAttribute

        return om.MFnTypedAttribute

    #-----------------------------------------|    Set

    def _setValue(self, matrix, **_):
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        fn = om.MFnMatrixData()
        mobj = fn.create()
        fn.set(om.MMatrix(matrix))
        plug.setMObject(mobj)

    #-----------------------------------------|    Get

    def _getValue(self, *, frame=None, **_):
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        kwargs = {}
        if frame is not None:
            kwargs['context'] = om.MDGContext(
                om.MTime(frame, unit=om.MTime.uiUnit())
            )
        mobj = plug.asMObject(**kwargs)
        fn = om.MFnMatrixData(mobj)
        return self.__datacls__(fn.matrix())

    #-----------------------------------------|    Default value

    def getDefaultValue(self):
        out = plugs['Attribute'].getDefaultValue(self)

        if isinstance(out, om.MObject):
            if out.isNull():
                return data['Matrix']()
            return data['Matrix'].fromApi(om.MFnMatrixData(out).matrix())
        return data['Matrix'].fromApi(out)

    def setDefaultValue(self, value):
        if self.isMulti():
            self = self[0]

        attrFn = self.__apimfn__()
        matrixFn = om.MFnMatrixData()
        mobj = matrixFn.create()
        matrixFn.set(data['Matrix'](value).api)
        attrFn.default = mobj
        return self

    #-----------------------------------------|    Mult

    def multiply(self, *others):
        T = plugs['Attribute']
        others = [T(x) for x in expand_tuples_lists(others)]
        if others:
            node = nodes.MultMatrix.createNode()
            self >> node.attr('matrixIn')[0]
            for i, other in enumerate(others, start=1):
                other >> node.attr('matrixIn')[i]
            return node.attr('matrixSum')
        return self

    mul = multiply

    def __mul__(self, other):
        other, shape, isPlug = _mm.info(other)
        if shape == 16:
            node = nodes.MultMatrix.createNode()
            self >> node.attr('matrixIn')[0]
            node.attr('matrixIn')[1].put(other, isPlug)
            return node.attr('matrixSum')
        return NotImplemented

    def __rmul__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 16:
            node = nodes.MultMatrix.createNode()
            node.attr('matrixIn')[0].put(other, isPlug)
            self >> node.attr('matrixIn')[1]
            return node.attr('matrixSum')

        if shape == 3:
            node = nodes.VectorProduct.createNode()
            node.attr('operation').set(3)
            node.attr('input1').put(other, isPlug)
            self >> node.attr('matrix')
            return node.attr('output')

        return NotImplemented

    #-----------------------------------------|    Forced point-matrix mult

    def __rxor__(self, other):
        other, shape, isPlug = _mm.info(other)

        if shape == 3:
            node = nodes.PointMatrixMult.createNode()
            node.attr('inPoint').put(other, isPlug)
            self >> node.attr('inMatrix')
            return node.attr('output')

        return NotImplemented

    #-----------------------------------------|    Misc matrix ops

    @cache_dg_output
    @short(reuse='re')
    def inverse(self):
        """
        :return: The inverse of this matrix.
        """
        node = nodes['InverseMatrix'].createNode()
        self >> node.attr('inputMatrix')
        return node.attr('outputMatrix')

    def __invert__(self):
        return self.inverse()

    #-----------------------------------------|    Row access

    def _createRowNetworkNode(self):
        with _nm.Name('axis_breakout'):
            node = nodes['Network'].createNode()

        _node = str(node)
        m.addAttr(_node, ln='outAxes', at='double3', multi=True, nc=3)

        for axis in 'XYZ':
            m.addAttr(_node, ln=f"outAxis{axis}", at='double', parent='outAxes')

        m.addAttr(_node, ln='outPosition', at='double3', nc=3)
        for axis in 'XYZ':
            m.addAttr(_node, ln=f'outPosition{axis}', at='doubleLinear',
                      parent='outPosition')

        self >> node.addAttr('sourceMatrix', at='message')
        return node

    def _getRowNetworkNode(self):
        for output in self.outputs(type='network', plugs=True):
            if output.type() == 'message' \
                    and output.attrName() == 'sourceMatrix':
                return output.node()
        return self._createRowNetworkNode()

    def getRow(self, index:Literal[0, 1, 2, 3]):
        """
        :param index: one of 0, 1, 2 or 3 (for position)
        :return: The vector or point for the specified row.
        """
        nw = self._getRowNetworkNode()
        if index == 3:
            plug = nw.attr('outPosition')
            if not plug.inputs():
                node = nodes['PointMatrixMult'].createNode()
                self >> node.attr('inMatrix')
                node.attr('output') >> plug
            return plug

        plug = nw.attr('outAxes')[index]

        if not plug.inputs():
            node = nodes['VectorProduct'].createNode()
            node.attr('operation').set(3)
            self >> node.attr('matrix')
            node.attr('input1').set([(1, 0, 0),
                                     (0, 1, 0),
                                     (0, 0, 1)][index])
            node.attr('output') >> plug
        return plug

    def getAxis(self, axis:Literal['x', 'y', 'z', '-x', '-y', '-z', 'w']):
        """
        :param axis: one of 'x', 'y', 'z', '-x', '-y', '-z' or 'w' (position)
        :return: The vector or point for the requested axis.
        """
        absAxis = axis.strip('-')
        vector = self.getRow('xyzw'.index(absAxis))
        if '-' in axis:
            vector = -vector
        return vector

    @property
    def x(self):
        return self.getRow(0)

    @property
    def y(self):
        return self.getRow(1)

    @property
    def z(self):
        return self.getRow(2)

    @property
    def w(self):
        return self.getRow(3)

    #-----------------------------------------|    Filtering

    @short(translate='t',
           rotate='r',
           scale='s',
           shear='sh')
    def _pick(self,
              translate=None,
              rotate=None,
              scale=None,
              shear=None):
        translate, rotate, scale, shear = resolve_flags(
            translate, rotate, scale, shear
        )
        if any([translate, rotate, scale, shear]):
            if all([translate, rotate, scale, shear]):
                return self

            node = nodes['PickMatrix'].createNode()
            for attrName, value in zip(
                    ('useTranslate', 'useRotate', 'useScale', 'useShear'),
                    (translate, rotate, scale, shear)
            ):
                node.attr(attrName).set(value)
            self >> node.attr('inputMatrix')
            return node.attr('outputMatrix')

        return nodes['HoldMatrix'].createNode().attr('outMatrix')

    @short(translate='t',
           rotate='r',
           scale='s',
           shear='sh')
    def explode(self, scale=None, shear=None, rotate=None, translate=None):
        """
        Returns filtered matrices in order of multiplication, i.e.:
            scale, shear, rotate, translate
        """
        translate, rotate, scale, shear = resolve_flags(
            translate, rotate, scale, shear
        )

        out = []

        if scale:
            out.append(self.asScaleMatrix())

        if shear:
            out.append(self.asShearMatrix())

        if rotate:
            out.append(self.asRotateMatrix())

        if translate:
            out.append(self.asTranslateMatrix())

        return tuple(out)

    @short(translate='t',
           rotate='r',
           scale='s',
           shear='sh',
           default='d')
    def pick(self,
             translate=None,
             rotate=None,
             scale=None,
             shear=None,
             default=None):
        """
        Filters this matrix.

        :param translate/t: include translate information
        :param rotate/r: include rotate information
        :param scale/s: include scale information
        :param shear/sh: include shear information
        :param default: a fallback matrix source for omitted information;
            defaults to None
        :return: The filtered matrix.
        """
        if default is None:
            return self._pick(t=translate, r=rotate, s=scale, sh=shear)
        default, _, defaultIsPlug = _mm.info(default, data['Matrix'])

        translate, rotate, scale, shear = resolve_flags(
            translate, rotate, scale, shear
        )
        if any([translate, rotate, scale, shear]):
            if all([translate, rotate, scale, shear]):
                return self
            matrices = []

            if scale:
                matrices.append(self.asScaleMatrix())
            else:
                matrices.append(default.asScaleMatrix())

            if shear:
                matrices.append(self.asShearMatrix())
            else:
                matrices.append(default.asShearMatrix())

            if rotate:
                matrices.append(self.asRotateMatrix())
            else:
                matrices.append(default.asRotateMatrix())

            if translate:
                matrices.append(self.asTranslateMatrix())
            else:
                matrices.append(default.asTranslateMatrix())

            node = nodes['MultMatrix'].createNode()
            for i, matrix in enumerate(matrices):
                matrix >> node.attr('matrixIn')[i]

            return node.attr('matrixSum')
        return default if defaultIsPlug else default.asPlug()

    @cache_dg_output
    def asTranslateMatrix(self):
        """
        :return: A filtered version of this matrix.
        """
        with _nm.Name('extract_t'):
            out = self._pick(t=True)
        return out

    @cache_dg_output
    def asRotateMatrix(self):
        """
        :return: A filtered version of this matrix.
        """
        with _nm.Name('extract_r'):
            out = self._pick(r=True)
        return out

    @cache_dg_output
    def asTranslateRotateMatrix(self):
        """
        :return: A filtered version of this matrix.
        """
        with _nm.Name('extract_tr'):
            out = self._pick(t=True, r=True)
        return out

    @cache_dg_output
    def asScaleMatrix(self):
        """
        :return: A filtered version of this matrix.
        """
        with _nm.Name('extract_s'):
            out = self._pick(s=True)
        return out

    @cache_dg_output
    def asShearMatrix(self):
        """
        :return: A filtered version of this matrix.
        """
        return self._pick(sh=True)

    @cache_dg_output
    def asScaleMatrixFromMagnitudes(self):
        """
        :return: A scale matrix constructed strictly from the magnitudes of
            the base vectors.
        """
        node = nodes['FourByFourMatrix'].createNode()
        self.x.length() >> node.attr('in00')
        self.y.length() >> node.attr('in11')
        self.z.length() >> node.attr('in22')
        return node.attr('output')

    #-----------------------------------------|    FourByFour utils

    @cached_property
    def isFFOutput(self) -> bool:
        """
        :return: True if this is the ``output`` plug on a ``fourByFourMatrix``
            node.
        """
        node = self.node()
        return node.nodeType() == 'fourByFourMatrix' \
            and self.longName() == 'output'

    def asFourByFourMatrix(self, reuse:bool=False):
        """
        :param reuse: return ``self`` if this is already the output of a
            ``fourByFourMatrix`` node; defaults to False
        :return: A ``fourByFourMatrix`` node, with all of its rows extracted
            from this matrix.
        """
        if reuse and self.isFFOutput:
            return self

        node = nodes['FourByFourMatrix'].createNode()
        self.x >> node.x
        self.y >> node.y
        self.z >> node.z
        self.w >> node.w
        return node.attr('output')

    #-----------------------------------------|    Decomposition

    @short(rotateOrder='ro')
    def eulerRotation(self, rotateOrder=None):
        """
        :param rotateOrder: the rotate order; if omitted, and this is the
            local 'matrix' output on a transform node, the node's rotate order
            is used; defaults to 0 ('xyz')
        :return: The euler rotation component of this matrix.
        """
        node = nodes['DecomposeMatrix'].createNode()
        self >> node.attr('inputMatrix')
        if rotateOrder is None:
            rotateOrder = self.guessRotateOrder(True)
        rotateOrder >> node.attr('inputRotateOrder')
        return node.attr('outputRotate')

    @cache_dg_output
    def quaternion(self):
        """
        :return: The quaternion component of this matrix.
        """
        node = nodes['DecomposeMatrix'].createNode()
        self >> node.attr('inputMatrix')
        return node.attr('outputQuat')

    @short(rotateOrder='ro')
    def rotation(self, *, asQuaternion=False, rotateOrder=None):
        """
        :param rotateOrder: ignored if *asQuaternion* is True; the rotate order;
            if omitted, and this is the local 'matrix' output on a transform
            node, the node's rotate order is used; defaults to 0 ('xyz')
        :param asQuaternion: return a quaternion rather than an euler rotation;
            defaults to False
        :return: The rotation component of this matrix, as an euler rotation or
            quaternion.
        """
        if asQuaternion:
            return self.quaternion()
        return self.eulerRotation(rotateOrder)

    @cache_dg_output
    def averageScale(self):
        """
        :return: The average of the basis vector magnitudes.
        """
        node = nodes['PlusMinusAverage'].createNode()
        node.attr('operation').set('Average')
        self.x.length() >> node.attr('input1D')[0]
        self.y.length() >> node.attr('input1D')[1]
        self.z.length() >> node.attr('input1D')[2]
        return node.attr('output1D')

    def guessRotateOrder(self, plug:bool=False):
        """
        If this is the 'matrix' attribute on a transform node, returns the
        node's rotate order; otherwise, return 0 ('xyz').

        :param plug: return a plug where possible; defaults to False
        """
        node = self.node()
        if isinstance(node, nodes['Transform']) and self.attrName() == 'm':
            return node.attr('ro').get(plug=plug)

        return 0

    @short(rotateOrder='ro')
    def decompose(self, *, rotateOrder=None) -> dict:
        """
        Convenience method. Pipes this matrix into a ``decomposeMatrix``
        node and returns a dictionary with these keys:
        -   'node': The ``decomposeMatrix`` node
        -   'translate': the 'outputTranslate' plug
        -   'rotate': the 'outputRotate' plug
        -   'quaternion': the 'outputQuat' plug
        -   'scale': the 'outputScale' plug
        -   'shear': the 'outputShear' plug
        -   'rotateOrder': the 'inputRotateOrder' plug

        :param rotateOrder/ro: if this is None, then:
            -   If this is the 'matrix' or 'xformMatrix' output on a transform
                node, defaults to the node's 'rotateOrder' plug
            -   Otherwise, defaults to 0 ('xyz')
        :type rotateOrder/ro: a standard Maya rotate order enum integer, a
            rotate order string like 'yxz', or an enum plug
        """
        node = nodes['DecomposeMatrix'].createNode()
        self >> node.attr('inputMatrix')

        if rotateOrder is None:
            rotateOrder = self.guessRotateOrder(True)
        rotateOrder >> node.attr('inputRotateOrder')

        return {'translate': node.attr('outputTranslate'),
                'rotate': node.attr('outputRotate'),
                'scale': node.attr('outputScale'),
                'shear': node.attr('outputShear'),
                'quaternion': node.attr('outputQuat'),
                'rotateOrder': node.attr('inputRotateOrder')}

    @cache_dg_output
    def withNormalizedAxes(self):
        """
        :return: A version of this matrix where all the basis vectors are
            normalized.
        """
        if self.isFFOutput:
            src = self.node()
        else:
            src = self

        ff = nodes['FourByFourMatrix'].createNode()
        src.x.normal() >> ff.x
        src.y.normal() >> ff.y
        src.z.normal() >> ff.z
        src.w >> ff.w

        return ff.attr('output')

    #-----------------------------------------|    Application

    @short(translate='t',
           rotate='r',
           scale='s',
           shear='sh',
           compensatePivots='cp',
           compensateJointOrient='cjo',
           compensateRotateAxis='cra',
           compensateJointScale='cjs',
           worldSpace='ws',
           maintainOffset='mo')
    def decomposeAndApply(self,
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
                          maintainOffset=False):
        """
        Decomposes this matrix and uses it to drive one or more transforms.

        :param slaves: the slave transforms
        :param translate/t: drive translation
        :param rotate/r: drive rotation
        :param scale/s: drive scale
        :param shear/sh: drive shear
        :param compensatePivots/cp: compensate pivots to match Maya constraint
            behaviour; defaults to False
        :param compensateJointOrient/cjo: compensate joint orient; defaults to
            True
        :param compensateRotateAxis/cra: compensate rotate axis; defaults to
            False
        :param compensateJointScale/cjs compensate joint scale; defaults to
            True
        :param worldSpace/ws: apply in world space; defaults to False
        :param maintainOffset/mo: preserve original poses; defaults to False
        """
        #-------------------------------------|    Prep / early bail

        _Transform = nodes['Transform']

        slaves = [_Transform(slave) for slave in expand_tuples_lists(*slaves)]

        if not slaves:
            raise ValueError("no slaves specified")

        translate, rotate, scale, shear \
            = resolve_flags(translate, rotate, scale, shear)

        if not any([translate, rotate, scale, shear]):
            m.warning("no channels requested")
            return self

        #-------------------------------------|    Preprocessing

        matrix = self

        if maintainOffset:
            matrix = matrix.asOffset()

        #-------------------------------------|    Iterate

        for slave in slaves:
            _matrix = matrix

            if maintainOffset:
                _matrix = slave.getMatrix(worldSpace=worldSpace) * _matrix

            if worldSpace:
                _matrix *= slave.attr('parentInverseMatrix')[0]

            _compensatePivots = compensatePivots
            _compensateJointOrient = compensateJointOrient
            _compensateRotateAxis = compensateRotateAxis
            _compensateJointScale = compensateJointScale

            isJoint = slave.nodeType() == 'joint'

            if isJoint:
                _compensatePivots = False

                fast = not any([_compensateRotateAxis,
                                _compensateJointScale,
                                _compensateJointOrient])

            else:
                _compensateJointScale = _compensateJointOrient = False
                fast = not (_compensateRotateAxis or _compensatePivots)

            if fast:
                decomposition = _matrix.decompose(ro=slave.attr('ro'))

                for channel, state in zip(
                        ['translate', 'rotate', 'scale', 'shear'],
                        [translate, rotate, scale, shear]
                ):
                    if state:
                        dest = slave.attr(channel)

                        try:
                            decomposition[channel] >> dest
                        except:
                            m.warning("couldn't connect into {}".format(dest))
                            continue
            else:
                #-------------------------|    Disassemble

                tmtx = _matrix.pick(translate=True)

                if _compensateJointScale:
                    pismtx = slave.attr('inverseScale').asScaleMatrix()

                    _matrix = slave.attr('segmentScaleCompensate').ifElse(
                        _matrix * pismtx,
                        _matrix
                    ).asType(plugs['Matrix'])

                smtx = _matrix.pick(scale=True, shear=True)
                rmtx = _matrix.pick(rotate=True)

                #-------------------------|    Rotation compensations

                if _compensateRotateAxis:
                    ramtx = slave.attr('rotateAxis').asMatrix()
                    # ramtx = slave.getRotateAxisMatrix(plug=True)
                    rmtx = ramtx.inverse() * rmtx

                if _compensateJointOrient:
                    # jomtx = slave.getJointOrientMatrix(plug=True)
                    jomtx = slave.attr('jointOrient').asMatrix()
                    rmtx *= jomtx.inverse()

                #-------------------------|    Pivot compensations

                if _compensatePivots:
                    # Solve as Maya would
                    ramtx = slave.getRotateAxisMatrix(p=True)
                    spmtx = slave.attr('scalePivot').asTranslateMatrix()
                    stmtx = slave.attr('scalePivotTranslate'
                                       ).asTranslateMatrix()
                    rpmtx = slave.attr('rotatePivot').asTranslateMatrix()
                    rtmtx = slave.attr('rotatePivotTranslate'
                                       ).asTranslateMatrix()

                    partialMatrix = spmtx.inverse() * smtx * spmtx * stmtx \
                                    * rpmtx.inverse() * ramtx * rmtx * rpmtx \
                                    * rtmtx

                    # Capture and negate translation contribution
                    translateContribution = partialMatrix.pick(translate=True)
                    tmtx *= translateContribution.inverse()

                #-------------------------|    Reassemble & apply

                _matrix = smtx * rmtx * tmtx
                decomposition = _matrix.decompose(ro=slave.attr('ro'))

                for channel, state in zip(
                        ('translate', 'rotate', 'scale', 'shear'),
                        (translate, rotate, scale, shear)
                ):
                    if state:
                        source = decomposition[channel]
                        dest = slave.attr(channel)
                        try:
                            source >> dest
                        except:
                            m.warning("couldn't connect into {}".format(dest))
                            continue


    @short(worldSpace='ws',
           persistentCompensation='pc',
           preserveInheritsTransform='pit',
           maintainOffset='mo')
    def applyViaOpm(self,
                    *slaves,
                    worldSpace=False,
                    persistentCompensation=False,
                    preserveInheritsTransform=False,
                    maintainOffset=False):
        """
        Drives one or more transforms via `offsetParentMatrix` rather than
        decomposition.

        :param \*slaves: the transforms to drive
        :param worldSpace/ws: drive in world space; defaults to False
        :param persistentCompensation/pc: persistently compensate against the
            SRT channels; defaults to False
        :param preserveInheritsTransform/pit: don't turn off
            ``inheritsTransform``, detect the parent once instead; defaults to
            False
        :param maintainOffset/mo: preserve initial poses; defaults to False
        """
        _Transform = nodes['Transform']
        slaves = [_Transform(slave) for slave in expand_tuples_lists(*slaves)]

        if not slaves:
            raise ValueError("No slaves specified.")

        matrix = self

        if maintainOffset:
            matrix = matrix.asOffset()

        for slave in slaves:
            _matrix = matrix

            if maintainOffset:
                _matrix = slave.getMatrix(worldSpace=worldSpace) * _matrix

            if worldSpace:
                if preserveInheritsTransform:
                    pnt = slave.getParent()
                    if pnt:
                        _matrix *= pnt.attr('worldInverseMatrix')
                else:
                    slave.attr('inheritsTransform').set(False)
            _matrix = slave.attr('inverseMatrix').get(
                plug=persistentCompensation) * _matrix

            _matrix >> slave.attr('offsetParentMatrix')

    def asOffset(self):
        """
        Equivalent to ``self.get().inverse() * self``.
        """
        return self.get().inverse() * self

    @cache_dg_output
    def asCachedOffset(self):
        """
        Similar to :meth:`asOffset`, but reuses outputs. Best for rig builds
        where things won't move while getting built.
        """
        return self.get().inverse() * self

    #-----------------------------------------|    Misc inspections

    @cache_dg_output
    def determinant(self):
        """
        :return: The determinant of this matrix
        """
        node = nodes['Determinant'].createNode()
        self >> node.attr('input')
        return node.attr('output')

    @cache_dg_output
    def isFlipped(self) -> bool:
        """
        :return: True if any of the basis vectors in this matrix are facing in
            the opposite direction.
        """
        return self.determinant().lt(0.0)

    #-----------------------------------------|    Graph flow

    def hold(self):
        """
        Pipes this matrix into a ``holdMatrix`` node and returns the output.
        Useful for branch splits / assigning to different variables.
        """
        node = nodes['HoldMatrix'].createNode()
        self >> node.attr('inMatrix')
        return node.attr('outMatrix')

    #-----------------------------------------|    Blending

    def blend(self, other, weight=0.5):
        """
        Blends this matrix towards *other*.

        :param other: the matrix towards which to blend
        :param weight: a scalar value or plug for the blending factor; defaults
            to 0.5
        :return: The blended matrix.
        """
        node = nodes['BlendMatrix'].createNode()
        self >> node.attr('inputMatrix')
        slot = node.attr('target')[0]
        other >> slot.attr('targetMatrix')
        weight >> slot.attr('weight')
        return node.attr('outputMatrix')

    #-----------------------------------------|    Aiming

    @short(upVector='up',
           scale='s',
           reapplyMagnitudes='ram',
           stretchy='st')
    def aimTowards(self,
                   point,
                   aimAxis:str,
                   upAxis:str,
                   upVector=None, *,
                   scale=None,
                   reapplyMagnitudes=True,
                   stretchy=False):
        """
        :param point: the point towards which to aim; must be an attribute
        :param aimAxis: the axis to aim, e.g. 'x'
        :param upAxis: the up axis, e.g. 'z'
        :param upVector/up: if provided, must be an attribute; if omitted, it
            will be extracted from this matrix; defaults to None
        :param scale/s: a scaling factor for all matrix axes; defaults to None
        :param reapplyMagnitudes/ram: reuse vector magnitudes from this matrix;
            defaults to True
        :param stretchy/st: make the aim-aligned vector on the output matrix
            stretch; defaults to False
        :return: A version of this matrix aimed towards *point*.
        """
        Attribute = plugs['Attribute']
        point = Attribute(point)

        if upVector is None:
            upAxis = upAxis.strip('-')
            upVector = self.getAxis(upAxis)
        else:
            upVector = Attribute(upVector)
            if upAxis.startswith('-'):
                upVector *= -1.0
                upAxis = upAxis[1:]

        if scale is not None:
            scale = Attribute(scale)

        startPoint = self.w

        if aimAxis.startswith('-'):
            aimVector = startPoint - point
            aimAxis = aimAxis[1:]
        else:
            aimVector = point - startPoint

        matrix = _mm.createOrthoMatrix(
            aimAxis, aimVector,
            upAxis, upVector,
            w=startPoint
        )

        if stretchy:
            ff = nodes['FourByFourMatrix'].createNode()

            for axis, field in zip('xyz', ('in00', 'in11','in22')):
                if axis == aimAxis:
                    mag = aimVector.length()
                    mag /= mag()
                    if reapplyMagnitudes:
                        mag *= self.getAxis(axis).length()
                    elif scale is not None:
                        mag *= scale
                    mag >> ff.attr(field)
                else:
                    factors = []

                    if reapplyMagnitudes:
                        factors.append(self.getAxis(axis).length())

                    if scale is not None:
                        factors.append(scale)

                    mag = collapseFactors(factors)
                    if mag is not None:
                        mag >> ff.attr(field)

            smtx = ff.attr('output')
            matrix = smtx * matrix.pick(t=True, r=True)
        else:
            factors = []
            if reapplyMagnitudes:
                factors.append(self.pick(s=True))

            if scale:
                ff = nodes['FourByFourMatrix'].createNode()
                for axis, field in zip('xyz', ('in00', 'in11','in22')):
                    scale >> ff.attr(field)
                factors.append(ff.attr('output'))

            smtx = collapseFactors(factors)
            if smtx is not None:
                matrix = smtx * matrix.pick(t=True, r=True)
        return matrix