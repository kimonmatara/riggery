"""
Base tools for creating controls.
"""

from typing import Optional
from contextlib import nullcontext
from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists
from riggery.general.strings import int_to_letter
from ..lib import names as _nm
from ..datatypes import __pool__ as data
from ..nodetypes import __pool__ as nodes

GLOBAL_SHAPE_SCALE = 8.0

@short(matrix='m',
       worldSpace='ws',
       parent='p',
       keyable='k',
       channelBox='cb',
       pickWalkParent='pwp',
       zeroChannels='zc',
       offsetGroups='og',
       shape='sh',
       shapeScale='ss',
       shapeColor='sc',
       shapeAxisRemap='sar',
       displayHandle='dh',
       asControl='ac',
       uniformScale='us',
       detailedReturn='det')
def createControl(*,
                  matrix=None,
                  worldSpace:bool=False,
                  parent=None,
                  keyable=None,
                  channelBox=None,
                  shapeScale:float=1.0,
                  shape=None,
                  shapeColor=None,
                  shapeAxisRemap=None,
                  pickWalkParent=None,
                  zeroChannels:bool=True,
                  rotateOrder=0,
                  offsetGroups=None,
                  asControl:bool=True,
                  displayHandle=None,
                  uniformScale:bool=False,
                  detailedReturn:bool=False):
    """
    Creates and returns a single control.

    :param matrix: the control matrix; defaults to identity
    :param worldSpace: apply the matrix in world-space (ignoring the parent);
        defaults to False
    :param parent/p: the destination parent
    :param keyable/k: a list of keyable channels; if both this and *channelBox*
        are omitted, *keyable* defaults to ``['t', 'r', 'ro']``
    :param channelBox/cb: a list of settable channels; defaults to None
    :param uniformScale/us: creates a ``uniformScale`` attribute to drive all
        scale channels; ignored if 'scale' or 's' are not in *keyable* or
        *channelBox*; defaults to False
    :param shape/sh: a library control shape; defaults to None
    :param shapeScale/ss: a scaling factor for the library control shape;
        defaults to 1.0
    :param shapeColor/sc: either a string lookup (like 'red') or a color index
        for the shape color; defaults to None
    :param shapeAxisRemap/sar: two or four letter axes, defining pairwise remaps
        for the control shape; defaults to None
    :param pickWalkParent/pwp: a pick-walk parent for the control; defaults to
        None
    :param zeroChannels/zc: ignored if *offsetGroups* is defined; forces zeroing
        by editing the control's ``offsetParentMatrix`` attribute; defaults to
        True
    :param rotateOrder/ro: the control's rotate order on build; defaults to 0
        ('xyz')
    :param offsetGroups/og: one or more suffixes for offset groups; defaults to
        None
    :param asControl/ac: if this is True, features like controller tagging,
        shapes etc. will be omitted; defaults to False
    :param displayHandle/dh: display a simple crosshair for selection; defaults
        to True if *asControl* is True and *shape* is None
    :return: The main control transform.
    """
    details = {}

    shapeScale = shapeScale * ShapeScale.__scale_factor__ * GLOBAL_SHAPE_SCALE

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
            xf.setControlShape(shape,
                               shapeScale=shapeScale,
                               shapeColor=shapeColor,
                               shapeAxisRemap=shapeAxisRemap)

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
    return details if detailedReturn else xf

@short(matrix='m',
       worldSpace='ws',
       parent='p',
       keyable='k',
       channelBox='cb',
       pickWalkParent='pwp',
       pickWalkStack='pws',
       zeroChannels='zc',
       offsetGroups='og',
       shape='sh',
       shapeScale='ss',
       shapeColor='sc',
       shapeAxisRemap='sar',
       insetScalingFactor='isf',
       asControl='ac')
def createControlStack(numControls:int, *,
                       matrix=None,
                       worldSpace:bool=False,
                       parent=None,
                       keyable=None,
                       channelBox=None,
                       shapeScale:float=1.0,
                       shape=None,
                       shapeColor=None,
                       insetScalingFactor:float=0.75,
                       shapeAxisRemap=None,
                       pickWalkParent=None,
                       pickWalkStack=True,
                       zeroChannels:bool=True,
                       rotateOrder=0,
                       offsetGroups=None,
                       displayHandle=None,
                       asControl:bool=True):
    """
    Creates a stack of inset controls. Options like *offsetGroups* only apply to
    the root control. See :func:`createControl` for full parameter information.

    :param numControls: the overall number of controls to create, including
        insets
    :param insetScalingFactor: a shape scaling factor for each inset control;
        defaults to 0.75
    :return: All the controls, in a list. The outermost (top) control will be
        first on the list (index 0). The innermost control will be last.
    """
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
                      'shapeColor': shapeColor,
                      'shapeAxisRemap': shapeAxisRemap,
                      'shapeScale': shapeScale * (insetScalingFactor ** i),
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

            control = createControl(**kwargs)

            if not isRoot:
                sw = prev.addAttr('showInset', at='bool', cb=True, dv=False)
                for s in control.shapes:
                    sw >> s.attr('v')

        controls.append(control)

    return controls


class ShapeScale:
    __scale_factor__ = 1.0

    def __init__(self, scale:float):
        self._scale = scale

    def __enter__(self):
        self._prev = ShapeScale.__scale_factor__
        ShapeScale.__scale_factor__ *= self._scale
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        ShapeScale.__scale_factor__ = self._prev
        return False