from typing import Union, Generator, Literal, Optional, Iterable

def remap(value, oldMin, oldMax, newMin, newMax):
    oldSpan = oldMax - oldMin
    oldPartialSpan = value - oldMin
    ratio = oldPartialSpan / oldSpan
    newSpan = newMax - newMin
    return newMin + (newSpan * ratio)

def linear_interp(start, end, ratio) -> float:
    ratio = max(0, min(1.0, ratio))
    start, end, ratio = map(float, (start, end, ratio))
    return start + ((end-start) * ratio)

def cubic_interp(start, end, ratio) -> float:
    ratio = max(0, min(1.0, ratio))
    start, end, ratio = map(float, (start, end, ratio))
    ratio = ratio * ratio * (3 - 2 * ratio)
    return start + ((end-start) * ratio)

def quad_interp(start, end, ratio) -> float:
    ratio = max(0, min(1.0, ratio))

    if ratio <= 0.5:
        rm = remap(ratio, 0, 0.5, 0.0, 1.0)
        rm = rm ** 2
        ratio = remap(rm, 0.0, 1.0, 0.0, 0.5)
    else:
        rm = remap(ratio, 0.5, 1.0, 1.0, 0.0)
        rm = rm ** 2
        ratio = remap(rm, 1.0, 0.0, 0.5, 1.0)
    return start + ((end-start) * ratio)

def floatrange(minValue:Union[int, float],
               maxValue:Union[int, float],
               number:int):
    grain = 1.0 / (number-1)
    minValue = float(minValue)
    maxValue = float(maxValue)
    span = maxValue - minValue
    out = minValue
    ratio = 0.0

    for i in range(number):
        if i == number-1:
            out = min(out, maxValue)
        yield out
        ratio += grain
        out = minValue + (span * ratio)

def subdivide_int(num_anchors:int, iterations:int, inclusive:bool=True) -> int:
    """
    Given a number of 'anchors' (e.g. along a poly edge or curve), tells you how
    many you would be left with after applying a certain number of subdivisions.

    :param num_anchors: the starting number of nodes / anchors / elements; must
        be at least 2
    :param iterations: the number of times to subdivide *num_anchors*
    :param inclusive: return the original number + the number of anchors added
        through subdivision; if this is false, only the number contributed by
        subdivision will be returned; defaults to True
    """
    if num_anchors > 1:
        out = num_anchors - 2
        for i in range(iterations):
            out = out * 2 + 1
        if inclusive:
            out += 2
        return out
    raise ValueError('num anchors must be at least 2')

def subdivide_floats(floats:Iterable[float],
                     iterations:int=1,
                     inclusive:bool=True) -> list[float]:
    """
    :param floats: a list (or iterable) of float values
    :param iterations: the number of times to subdivide the floats list, adding
        inbetween values
    :param inclusive: if this is True, the returned numbers will include the
        originals; otherwise, only numbers contributed by subdivision will be
        included; defaults to True
    :return: The subdivided floats list.
    """
    floats = list(floats)

    out = []

    for thisFloat, nextFloat in zip(floats, floats[1:]):
        numRatios = subdivide_int(2, iterations)
        tweens = list(floatrange(thisFloat,
                                 nextFloat,
                                 subdivide_int(2, iterations)))[:-1]
        if not inclusive:
            tweens = tweens[1:]
        out += tweens

    if inclusive:
        out.append(floats[-1])

    return out

def distribute_samples(totalNumSamples:int,
                       numSegments:int,
                       minPerSegment:int=0) -> list[int]:
    """
    Distributes samples across a number of targets ('segments'). Useful for
    scenarios like distributing a total number of samples requested by the user
    across a number of curve segments (e.g. for up vector interpolation).

    Any remainder is distributed in 'staggered' fashion rather than bunching it
    up at either end of the segment group.

    :param totalNumSamples: the total number of samples
    :param numSegments: the number of segments to distribute the total number to
    :param minPerSegment: if distribution yields zero samples for some
        segments, raise it to this number, even if it would overshoot the
        requested *totalNumSamples*; defaults to 0
    :return: A list of numbers, where each number is the number of samples for
        that segment.
    """
    perSegment = totalNumSamples // numSegments
    remainder = totalNumSamples % numSegments
    allocations = [perSegment] * numSegments

    if remainder:
        for start in (0, 1):
            if remainder:
                for i in range(start, numSegments, 2):
                    if remainder:
                        allocations[i] += 1
                        remainder -=1
                    else:
                        break

    if minPerSegment > 0:
        allocations = [max(minPerSegment, x) for x in allocations]

    return allocations