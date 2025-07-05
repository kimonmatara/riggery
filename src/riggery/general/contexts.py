"""
Utilities for context managers.
"""
from .iterables import expand_tuples_lists

class nested:
    """
    Nests context manager instances. The return of ``__enter__`` can be caught
    as a tuple, e.g.:

    .. code-block:: python
        with nested(r.Name('alpha'), r.Name('beta')) as (n1, n2):
            r.nodes.Joint.createNode()
            # Result: alpha_beta_JOIN
    """
    def __init__(self, *contexts):
        """
        :param \*contexts: initialized context managers, packed or unpacked
        """
        self._contexts = expand_tuples_lists(*contexts)

    def __enter__(self):
        return [context.__enter__() \
                for context in self._contexts]

    def __exit__(self, exc_type, exc_val, exc_tb):
        for context in self._contexts[::-1]:
            context.__exit__(exc_type, exc_val, exc_tb)

        return False