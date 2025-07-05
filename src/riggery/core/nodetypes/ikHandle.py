from typing import Optional, Literal
import maya.cmds as m

from riggery.general.functions import short
from ..nodetypes import __pool__ as nodes
from ..lib import names as _nm
from ..elem import Elem
from ..lib import skel as _sk

def _resolveTwistAxis(axis):
    if isinstance(axis, str):
        return {'x': 'Positive X',
                '-x': 'Negative X',
                'y': 'Positive Y',
                '-y': 'Negative Y',
                'z': 'Positive Z',
                '-z': 'Negative Z'}.get(axis.lower(), axis)
    return axis


class IkHandle(nodes['Transform']):

    #------------------------------------|    Constructor(s)

    @classmethod
    @short(curve='c',
           upVector='up',
           name='n',
           parent='p')
    def create(cls,
               startJoint,
               endJoint,
               upVector=None, *,
               curve=None,
               parent=None,
               name:Optional[str]=None):
        """
        Creates an IK handle.

        :param startJoint: the handle start joint
        :param endJoint: the handle end joint (inclusive)
        :param upVector/up: if provided, will be used defined counterclockwise
            rotation for in-line chains; defaults to None
        :param curve/c: if provided, will set up an IK spline handle; defaults
            to None
        :param parent/p: an optional parent for the IK handle; defaults to None
        :param name/n: if omitted, Name blocks will be used
        :return: The configured IK handle.
        """
        #------------------------|    Resolve arguments

        chain = _sk.Chain.fromStartEnd(startJoint, endJoint)
        numJoints = len(chain)
        if numJoints < 2:
            raise ValueError("not enough joints")

        kwargs = {'startJoint': str(chain[0]),
                  'endEffector': str(chain[-1])}

        if curve is None:
            kwargs['solver'] = 'ikRPsolver' if numJoints > 2 else 'ikSCsolver'
        else:
            kwargs['solver'] = 'ikSplineSolver'
            kwargs['createCurve'] = False
            kwargs['rootOnCurve'] = True
            kwargs['parentCurve'] = False

        # Names
        if name is None:
            if _nm.Name.__elems__:
                handleName = _nm.Name.evaluate(
                    typeSuffix = _nm.TYPESUFFIXES['ikHandle']
                )
                effName = _nm.Name.evaluate(
                    typeSuffix = _nm.TYPESUFFIXES['ikEffector']
                )
            else:
                handleName = 'ikHandle1'
                effName = 'effector1'
        else:
            handleName = name
            effName = f"{handleName}_effector"

        kwargs['name'] = handleName

        if upVector is not None:
            chain.ikJitter(upVector)

        ikh, eff = map(Elem, m.ikHandle(**kwargs))
        eff.name = effName

        if parent is not None:
            ikh.parent = parent

        return ikh

    #------------------------------------|    Basic inspections

    @property
    def effector(self):
        """
        :return: The end-effector node.
        """
        return nodes['DagNode'](m.ikHandle(str(self), q=True, ee=True))

    @property
    def chain(self):
        """
        A :class:`~mango.lib.skel.Chain` instance for the driven joints,
        including the tip.
        """
        joints = list(map(nodes['DagNode'],
                          m.ikHandle(str(self), q=True, jointList=True)))
        inputs = self.effector.attr('tx').inputs(type='joint')
        if inputs:
            joints.append(inputs[0])
        return _sk.Chain(joints)

    #------------------------------------|    Config

    @short(downAxis='da')
    def setTwistVectors(self,
                        startUpVector,
                        endUpVector,
                        upAxis:Literal['x', '-x', 'y', '-y', 'z',
                            '-z', 0, 1, 2, 3, 4, 5],
                        downAxis:Literal['x', '-x', 'y', '-y', 'z', '-z',
                            0, 1, 2, 3, 4, 5, None]=None):
        """
        One-shot twist vector configuration.

        :param startUpVector: the root up vector; can be a plug
        :param endUpVector: the tip up vector; can be a plug
        :param upAxis: the twist aiming axis (required)
        :param downAxis: the 'bone' axis; if omitted, will be auto-detected
        """
        self.attr('dTwistControlEnable').set(True)
        self.attr('dWorldUpType').set(6)

        startUpVector >> self.attr('dWorldUpVector')
        endUpVector >> self.attr('dWorldUpVectorEnd')

        if downAxis is None:
            downAxis = self.chain.detectDownAxis()

        self.attr('forwardAxis').set(_resolveTwistAxis(downAxis))
        self.attr('upAxis').set(_resolveTwistAxis(upAxis))

        return self