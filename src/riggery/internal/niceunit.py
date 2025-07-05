from riggery.general.strings import uncap
import maya.api.OpenMaya as om

#---------------------------------------|    DISTANCE

DISTANCE_SHORTS = {
    'centimeters': 'cm',
    'millimeters': 'mm',
    'meters': 'm',
    'inches': 'in',
    'feet': 'ft',
    'kilometers': 'km'
}

DISTANCE_ENUMS = {}
DISTANCE_KEY_TO_VAL = {}
DISTANCE_VAL_TO_KEY = {}
NATIVE_DISTANCE_UNIT = om.MDistance.kCentimeters

def _initDistance():
    for k, v in om.MDistance.__dict__.items():
        if k.startswith('k'):
            longKey = uncap(k[1:])
            DISTANCE_ENUMS[longKey] = v
            DISTANCE_KEY_TO_VAL[longKey.lower()] = v

            try:
                shortKey = DISTANCE_SHORTS[longKey]
                DISTANCE_ENUMS[shortKey] = v
                DISTANCE_KEY_TO_VAL[shortKey.lower()] = v
                DISTANCE_VAL_TO_KEY[v] = shortKey
            except KeyError:
                DISTANCE_VAL_TO_KEY[v] = longKey

#---------------------------------------|    ANGLE

ROTORDERS = ['xyz', 'yzx', 'zxy', 'xzy', 'yxz', 'zyx']

def conformRotateOrder(rotateOrder) -> int:
    """
    :param rotateOrder: the rotate order argument to conform to an integer;
        must either be None (conformed to 0), an integer (passed-through)
        or a lowercase key like 'xzy'
    :return: The conformed rotate order.
    """
    if rotateOrder is None:
        return 0
    if isinstance(rotateOrder, int):
        return rotateOrder
    return ROTORDERS.index(rotateOrder)

ANGLE_SHORTS = {
    'radians': 'rad',
    'degrees': 'deg'
}

ANGLE_ENUMS = {}
ANGLE_KEY_TO_VAL = {}
ANGLE_VAL_TO_KEY = {}
NATIVE_ANGLE_UNIT = om.MAngle.kRadians

def _initAngle():
    for k, v in om.MAngle.__dict__.items():
        if k.startswith('k'):
            longKey = uncap(k[1:])
            ANGLE_ENUMS[longKey] = v
            ANGLE_KEY_TO_VAL[longKey.lower()] = v

            try:
                shortKey = ANGLE_SHORTS[longKey]
                ANGLE_ENUMS[shortKey] = v
                ANGLE_KEY_TO_VAL[shortKey.lower()] = v
                ANGLE_VAL_TO_KEY[v] = shortKey
            except KeyError:
                ANGLE_VAL_TO_KEY[v] = longKey

#---------------------------------------|    TIME

TIME_SHORTS = {
    'seconds': 'sec',
    'milliseconds': 'ms',
    'hours': 'hr'
}

TIME_ENUMS = {}
TIME_KEY_TO_VAL = {}
TIME_VAL_TO_KEY = {}
NATIVE_ANGLE_UNIT = om.MTime.kSeconds

def _initTime():
    for k, v in om.MTime.__dict__.items():
        if k.startswith('k'):
            longKey = uncap(k[1:])
            TIME_ENUMS[longKey] = v
            TIME_KEY_TO_VAL[longKey.lower()] = v

            try:
                shortKey = TIME_SHORTS[longKey]
                TIME_ENUMS[shortKey] = v
                TIME_KEY_TO_VAL[shortKey.lower()] = v
                TIME_VAL_TO_KEY[v] = shortKey
            except KeyError:
                TIME_VAL_TO_KEY[v] = longKey


_initDistance()
_initAngle()
_initTime()