"""
Base tools for creating controls.
"""

from typing import Optional, Union
from contextlib import nullcontext
from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists
from riggery.general.strings import int_to_letter
from ..lib.controlshapes import ShapeScale
from ..lib import names as _nm
from ..datatypes import __pool__ as data
from ..nodetypes import __pool__ as nodes

GLOBAL_SHAPE_SCALE = 8.0

@short(worldSpace='ws',
       keyable='k',
       channelBox='cb',
       axisRemap='ar',
       pickWalkParent='pwp',
       zeroChannels='zc',
       rotateOrder='ro',
       offsetGroups='og',
       asControl='ac')
def createControl(
        *,
        matrix:Optional[list[float]]=None,
        worldSpace:bool=False,
        parent:Optional[Union[str, 'r.nodes.Transform']]=None,
        keyable:Optional[Union[str, list[str]]]=None,
        channelBox:Optional[Union[str, list[str]]]=None,

        shape:Optional[str]=None,
        color:Optional[Union[str, int]]=None,
        axisRemap:Optional[list[str]]=None,

        pickWalkParent:Optional[Union[str, 'r.nodes.DependNode']]=None,
        zeroChannels:bool=True,
        rotateOrder:Union[int, str]=0,
        offsetGroups:Optional[Union[str, list[str]]]=None,
        asControl:bool=True,
        displayHandle:Optional[bool]=None,
        uniformScale:bool=False,
        detailReturn:bool=False
):
    details = {}

    if keyable:
        keyable = expand_tuples_lists(keyable)
    else:
        keyable = []

    if channelBox:
        channelBox = expand_tuples_lists(channelBox)
    else:
        channelBox = []

    typeSuffix = _nm.CONTROLSUFFIX \
        if asControl else _nm.TYPESUFFIXES['transform']
    name = _nm.Name.evaluate(typeSuffix=typeSuffix)

    zeroChannels = zeroChannels and not offsetGroups

    kwargs = {'name': name,
              'parent': parent,
              'rotateOrder': rotateOrder,
              'zeroChannels': zeroChannels,
              'matrix': matrix,
              'worldSpace': worldSpace}

    if asControl:
        if shape is None:
            if displayHandle is None:
                kwargs['displayHandle'] = True

    details['control'] = xf = nodes['Transform'].create(**kwargs)

    if offsetGroups:
        details['offsetGroups'] = xf.createOffsetGroups(offsetGroups)

    if asControl:
        xf.isControl = True

        if pickWalkParent:
            xf.pickWalkParent = pickWalkParent

        if shape:
            xf.setControlShape(shape, color=color, axisRemap=axisRemap)

        if displayHandle:
            xf.attr('displayHandle').set(True)

    if not (keyable or channelBox):
        keyable = ['t', 'r', 'ro']

    xf.maskAnimAttrs(keyable=keyable, channelBox=channelBox)

    if uniformScale:
        asKeyable = asChannelBox = False

        if 's' in keyable or 'scale' in keyable:
            asKeyable = True
        elif 's' in channelBox or 'scale' in channelBox:
            asChannelBox = True

        if asKeyable or asChannelBox:
            driver = xf.addAttr('uniformScale', min=1e-4, max=100, dv=1.0)
            driver.setFlag('k' if asKeyable else 'cb', True)
            for chan in 'xyz':
                target = xf.attr(f's{chan}')
                driver >> target
                target.disable()

    return details if detailReturn else xf

@short(matrix='m',
       worldSpace='ws',
       parent='p',
       keyable='k',
       channelBox='cb',
       pickWalkParent='pwp',
       pickWalkStack='pws',
       zeroChannels='zc',
       offsetGroups='og',
       axisRemap='ar',
       insetScalingFactor='isf',
       asControl='ac')
def createControlStack(
        numControls:int, *,
        matrix:Optional[list[float]]=None,
        worldSpace:bool=False,
        parent:Optional[Union[str, 'nodes.Transform']]=None,
        keyable:Optional[Union[str, list[str]]]=None,
        channelBox:Optional[Union[str, list[str]]]=None,
        shape:Optional[str]=None,
        color:Optional[Union[str, int]]=None,
        insetScalingFactor:float=0.75,
        axisRemap:Optional[list[str]]=None,
        pickWalkParent:Optional[Union[str, 'nodes.DependNode']]=None,
        pickWalkStack:bool=True,
        zeroChannels:bool=True,
        rotateOrder:Union[str, int]=0,
        offsetGroups:Optional[Union[str, list[str]]]=None,
        displayHandle:Optional[bool]=None,
        asControl:bool=True
):
    controls = []

    for i in range(numControls):
        if numControls < 2:
            ctx = nullcontext()
        else:
            ctx = _nm.Name(int_to_letter(i))

        with ctx:

            kwargs = {'keyable': keyable,
                      'channelBox': channelBox,
                      'shape': shape,
                      'color': color,
                      'axisRemap': axisRemap,
                      'rotateOrder': rotateOrder,
                      'displayHandle': displayHandle,
                      'asControl': asControl}

            isRoot = i == 0

            if isRoot:
                kwargs.update({'zeroChannels': zeroChannels,
                               'matrix': matrix,
                               'worldSpace': worldSpace,
                               'parent': parent,
                               'pickWalkParent': pickWalkParent,
                               'offsetGroups': offsetGroups})
            else:
                prev = controls[i-1]
                kwargs['parent'] = prev
                if pickWalkStack:
                    kwargs['pickWalkParent'] = prev

            with ShapeScale(insetScalingFactor ** i):
                control = createControl(**kwargs)

            if not isRoot:
                sw = prev.addAttr('showInset', at='bool', cb=True, dv=False)
                for s in control.shapes:
                    sw >> s.attr('v')

        controls.append(control)

    return controls