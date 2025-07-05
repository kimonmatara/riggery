from typing import Union, Optional

from riggery.general.functions import short
import riggery.core.lib.skel as _sk

from ..nodetypes import __pool__ as nodes


class Joint(nodes['Transform']):

    #------------------------------------------|    Constructor(s)

    @classmethod
    @short(name='n',
           matrix='m',
           rotateOrder='ro',
           parent='p',
           worldSpace='ws',
           freezeRotate='fr',
           displayLocalAxis='dla')
    def create(cls, *,
               name:Optional[str]=None,
               matrix=None,
               rotateOrder:Union[int, str]=0,
               parent=None,
               worldSpace:bool=False,
               freezeRotate:bool=True,
               displayLocalAxis:bool=True):
        """
        :param name/n: if omitted, defaults to Name blocks
        :param matrix/m: the initial node matrix; defaults to identity
        :param parent/p: a destination parent; defaults to None
        :param rotateOrder/ro: the initial rotate order; defaults to 'xyz'
        :param displayLocalAxis/dla: display the local transformation axes;
            defaults to True
        :param freezeRotate/fr: zero-out rotation (but keep joint orient);
            defaults to True
        :param worldSpace/ws: apply *matrix* in world-space; defaults to
            False
        :return: The transform node.
        """
        node = super().create(name=name,
                              matrix=matrix,
                              rotateOrder=rotateOrder,
                              parent=parent,
                              worldSpace=worldSpace,
                              displayLocalAxis=displayLocalAxis)

        if freezeRotate:
            node.makeIdentity(rotate=True, apply=True, jointOrient=False)

        return node

    @classmethod
    @short(name='n',
           parent='p',
           worldSpace='ws')
    def createFromMacro(cls,
                        macro:dict, *,
                        name:str=None,
                        parent=None,
                        worldSpace=False):
        """
        Recreates a joint using the type of dictionary returned by
        :meth:`Joint.macro`.

        :param macro: the macro to use
        :param name/n: an optional name override; defaults to name blocks
        :param parent/p: an optional destination parent; defaults to None
        :param worldSpace/ws: apply the matrix information in world-space;
            defaults to False
        :return: The constructed joint.
        """
        joint = nodes['Joint'].createNode(name=name)

        if parent is not None:
            joint.parent = parent

        for key in ('jointOrient', 'rotateAxis',
                    'offsetParentMatrix', 'displayLocalAxis',
                    'radius', 'rotateOrder'):
            joint.attr(key).set(macro[key])

        if worldSpace:
            joint.setMatrix(macro['worldMatrix'])
        else:
            joint.setMatrix(macro['matrix'])

        return joint

    #------------------------------------------|    Serialization

    def macro(self) -> dict:
        """
        :return: A dictionary of serializable data that can be used by
            :meth:`fromMacro` to recreate the joint.
        """
        return {'matrix': self.attr('matrix')(),
                'worldMatrix': self.attr('worldMatrix')(),
                'jointOrient': self.attr('jointOrient')(),
                'rotateAxis': self.attr('rotateAxis')(),
                'offsetParentMatrix': self.attr('offsetParentMatrix')(),
                'displayLocalAxis': self.attr('displayLocalAxis')(),
                'radius': self.attr('radius')(),
                'rotateOrder': self.attr('rotateOrder')()}

    def cleanCopy(self):
        """
        :return: A cleanly-rebuilt copy of this joint, under the same parent.
        """
        return self.createFromMacro(self.macro(), parent=self.parent)

    #------------------------------------------|    DAG

    def findRootJoint(self):
        """
        Note that this may return ``self``.
        """
        lastVisited = None
        for parent in self.parents:
            if isinstance(parent, Joint):
                lastVisited = parent
                continue
            return self if lastVisited is None else lastVisited

    #------------------------------------------|    Constraints

    # def attachWithoutSkew(self, slave, decompose=False):
    #     # This works, but too many damn steps
    #
    #     slave = nodes['DagNode'](slave)
    #     iniPose = slave.getMatrix(worldSpace=True)
    #     tmtx = (slave.worldPosition()
    #             ^ self.attr('wm').asOffset()).asTranslateMatrix()
    #     rmtx = self.attr('wm').pick(r=True)
    #     smtx = self.attr('inverseScale').asScaleMatrix(
    #         ).inverse() * self.attr('pm')[0].pick(s=True)
    #     mtx = smtx * rmtx * tmtx
    #     if decompose:
    #         mtx.decomposeAndApply(slave, mo=True, ws=True)
    #     else:
    #         mtx.applyViaOpm(slave, mo=True, ws=True)
    #
    #     return self

    #------------------------------------------|    Skel

    def chainFromHere(self, end=None):
        if end is None:
            return _sk.Chain.fromStart(self)
        return _sk.Chain.fromStartEnd(self, end)

    def boneFromHere(self):
        children = list(self.iterChildren(type='joint'))
        num = len(children)
        if num == 1:
            return _sk.Chain([self, children[0]])
        raise TypeError('no unambiguous joint child')