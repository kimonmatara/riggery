from functools import reduce

def deep_merge_dicts(*dicts) -> dict:
    """
    Merges dictionaries and their sub-dictionaries. A sort of 'deep update'.
    Updates will happen first (left) to last (right).

    :return: The merged dictionary.
    """
    numDicts = len(dicts)

    if numDicts == 0:
        raise ValueError("no dictionaries provided")

    if numDicts == 1:
        return dicts[0].copy()

    def merge_two(d1, d2):
        out = d1.copy()

        for k2, v2 in d2.items():
            try:
                v1 = out[k2]
            except KeyError:
                out[k2] = v2
                continue

            if isinstance(v1, dict) and isinstance(v2, dict):
                v = merge_two(v1, v2)
            else:
                v = v2

            out[k2] = v

        return out

    return reduce(lambda x, y: merge_two(x, y), dicts)

def deep_intersect_dicts(*dicts) -> dict:
    """
    Deep-intersects dictionaries.

    :return: A dictionary that only contains keys common to the dictionaries and
        and dictionaries at the same depth. Values will be updated first (left)
        to last (right).
    """
    numDicts = len(dicts)

    if numDicts == 0:
        raise ValueError("no dictionaries provided")

    if numDicts == 1:
        return dicts[0].copy()

    def intersect_two(d1, d2):
        out = {}

        for k1, v1 in d1.items():
            try:
                v2 = d2[k1]
            except KeyError:
                continue

            if isinstance(v1, dict) and isinstance(v2, dict):
                v = intersect_two(v1, v2)
            else:
                v = v2

            out[k1] = v

        return out

    return reduce(lambda x, y: intersect_two(x, y), dicts)