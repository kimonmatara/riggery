import json
from copy import deepcopy
from itertools import pairwise, chain
from typing import Optional, Iterator, Iterable, Callable, Any

from riggery.general.iterables import without_duplicates
from .functions import resolve_flags


class DagBase:

    #------------------------------------|    Constructor(s)

    @classmethod
    def from_shorthand(cls,
                       shorthand:Iterable[str|Iterable[str]]) -> 'DagBase':
        """
        Where *shorthand* is an iterable of strings or lists of strings. If a
        member is a string, it will be added to the graph as an unmoored node.
        Otherwise, if it's an iterable of strings, the iterable will be added
        as a chain of connected nodes.
        """
        out = cls()

        for item in shorthand:
            if isinstance(item, str):
                out.add(item)
            else:
                out.connect(*item, add_nodes=True)

        return out

    #------------------------------------|    Init

    def __init__(self,
                 data:Optional[dict[str, list[str]]]=None, /):
        if data is None:
            data = {}
        self._data = data

    #------------------------------------|    Errors

    class UnrecognizedNodeError(Exception):...
    class CycleError(Exception):...

    #------------------------------------|    General membership

    def __len__(self):
        return len(list(self.nodes()))

    def nodes(self) -> Iterator[str]:
        """
        Yields all the nodes in the graph. Order is historical, and not
            related to evaluation.
        """
        visited = set()

        for dest_node, src_nodes in self._data.items():
            if dest_node not in visited:
                visited.add(dest_node)
                yield dest_node
            for src_node in src_nodes:
                if src_node not in visited:
                    visited.add(src_node)
                    yield src_node

    def add(self, *nodes_to_add):
        existing = set(self.nodes())

        for node_to_add in nodes_to_add:
            if node_to_add not in existing:
                self._data[node_to_add] = []
                existing.add(node_to_add)

    def _input_nodes(self) -> Iterator[str]:
        """Yields nodes that are inputs for other nodes."""
        yield from without_duplicates(chain(*self._data.values()))

    def roots(self) -> Iterator[str]:
        """Yields nodes that have no inputs."""
        for node in self.nodes():
            if not self._data.get(node):
                yield node

    def tips(self) -> Iterator[str]:
        """Yields nodes that have no outputs."""
        input_nodes = set(self._input_nodes())

        for node in self.nodes():
            if node not in input_nodes:
                yield node

    #------------------------------------|    Inputs / upstream

    def inputs(self, node:str) -> Iterator[str]:
        yield from self._data.get(node, [])

    def upstream(self, end_node:str, visited:Optional[set[str]]=None, /):
        if visited is None:
            visited = set()

        for input_node in self.inputs(end_node):
            if input_node not in visited:
                visited.add(input_node)
                yield input_node
                yield from self.upstream(input_node, visited)

    #------------------------------------|    Outputs / downstream

    def outputs(
            self,
            src_node:str,
            _outputs_cache:Optional[dict[str, list[str]]]=None, /
    ) -> Iterator[str]:
        """Yields nodes that are outputs to *src_node*."""
        if _outputs_cache is None:
            for dest_node, src_nodes in self._data.items():
                if dest_node == src_node:
                    continue
                if src_node in src_nodes:
                    yield dest_node
        else:
            yield from _outputs_cache[src_node]

    def downstream(
            self,
            start_node:str,
            _visited:Optional[set[str]]=None,
            _outputs_cache:Optional[dict[str, list[str]]]=None
    ) -> Iterator[str]:
        if _outputs_cache is None:
            _outputs_cache = {node:list(self.outputs(node))
                              for node in self.nodes()}

        if _visited is None:
            _visited = set()

        for out_node in self.outputs(start_node, _outputs_cache):
            if out_node not in _visited:
                _visited.add(out_node)
                yield out_node
                yield from self.downstream(out_node, _visited, _outputs_cache)

    #------------------------------------|    Edge editing

    def connect(self,
                *node_chain,
                add_nodes:bool=False,
                _prevent_partial_edits:bool=True):
        """
        :param node_chain: the nodes to connect, in a chain
        :param add_nodes: if this is True, then nodes will be added to the
            graph as required; defaults to False
        :raises UnrecognizedNodeError: node is not a member of the graph
        :param _prevent_partial_edits: if one of the attempted connections
            throws a cycle error, reverts preceding connections before
            raising; defaults to True
        """
        num = len(node_chain)
        if num < 2:
            raise ValueError("need at least two nodes")

        if not add_nodes:
            for node in set(node_chain):
                if node not in self.nodes():
                    raise self.UnrecognizedNodeError(node)

        _prevent_partial_edits = _prevent_partial_edits and num > 2

        if _prevent_partial_edits:
            backup = deepcopy(self._data)

        try:
            for src_node, dest_node in pairwise(node_chain):
                if (src_node == dest_node
                        or dest_node in self.upstream(src_node)):
                    raise self.CycleError('{} -> {}'.format(src_node,
                                                            dest_node))

                pool = self._data.setdefault(dest_node, [])

                if src_node not in pool:
                    pool.append(src_node)

        except self.CycleError as e:
            if _prevent_partial_edits:
                self._data.clear()
                self._data.update(backup)
            raise e

    def disconnect(self, *node_chain):
        """Disconnects nodes that are connected in the specified chain."""
        orig_nodes = list(self.nodes())

        for src_node, dest_node in pairwise(node_chain):
            try:
                self._data[dest_node].remove(src_node)
            except (KeyError, ValueError):
                continue

        self.add(*orig_nodes)

    def unmoor_all(self):
        """Removes all connections in the graph."""
        orig_nodes = list(self.nodes())
        self._data.clear()
        self.add(*orig_nodes)

    def unmoor(self,
               *nodes,
               inputs:Optional[bool]=None,
               outputs:Optional[bool]=None):
        """
        The *inputs* / *outputs* arguments are evaluated by-omission. If both
        are omitted, both default to True. If only one is specified, the other
        defaults to False.
        """
        if not nodes:
            raise ValueError("no nodes specified")

        nodes = set(nodes)
        orig_nodes = list(self.nodes())

        inputs, outputs = resolve_flags(inputs, outputs)

        if inputs:
            for node in nodes:
                self._data.pop(node, None)

        if outputs:
            for src_nodes in self._data.values():
                src_nodes[:] = [src_node for src_node in src_nodes
                                if src_node not in nodes]

        self.add(*orig_nodes)

    #------------------------------------|    Sequence calculations

    def sequence_to(self, target_node:str) -> list[str]:
        if target_node not in self.nodes():
            raise self.UnrecognizedNodeError(target_node)

        out = []

        def chase(node:str):
            out.append(node)
            for in_node in self.inputs(node):
                chase(in_node)

        chase(target_node)

        return list(without_duplicates(reversed(out)))

    def sequence(self) -> list[str]:
        return list(
            without_duplicates(
                chain.from_iterable(
                    self.sequence_to(tip) for tip in self.tips()
                )
            )
        )

    #------------------------------------|    Serialization, comparisons

    def canonical(self) -> list[tuple[str, tuple[str, ...]]]:
        return [(dest_node, tuple(src_nodes))
                for dest_node, src_nodes in self._data.items()]

    def to_json(self) -> str:
        data = [[dest_node, src_nodes]
                for dest_node, src_nodes in self._data.items()]
        return json.dumps(data, indent=4)

    @classmethod
    def from_json(cls, data:str) -> 'DagBase':
        data = json.loads(data)
        graph = cls()

        for dest_node, src_nodes in data:
            if src_nodes:
                for src_node in src_nodes:
                    graph.connect(src_node, dest_node, add_nodes=True)
            else:
                graph.add(dest_node)

        return graph

    def copy(self) -> 'DagBase':
        return type(self)(deepcopy(self._data))

    def __eq__(self, other):
        return isinstance(other,
                          DagBase) and self.canonical() == other.canonical()

    def __bool__(self):
        return bool(self._data)

    #------------------------------------|    Repr

    def __repr__(self) -> str:
        return "{}({})".format(type(self).__name__, repr(self._data))


class DagRunner(DagBase):
    """
    Abstract class. Dirty management relies on the interplay between the
    embedded ``runner`` callable and :meth:`get_dirty`.

    Subclass, implement :meth:`get_dirty` to return a value based on external
    conditions (check upstream too), and then pass-in a ``runner`` callable
    that will alter those external conditions in such a way that
    :meth:`get_dirty` will reflect them.
    """
    #------------------------------------|    Constructor(s)

    @classmethod
    def from_shorthand(cls,
                       shorthand:Iterable[str|Iterable[str]], *,
                       runner:Optional[Callable[[str], Any]]=None) -> 'DagBase':
        out = super().from_shorthand(shorthand)
        out.runner = runner
        return out

    #------------------------------------|    Init

    def __init__(self,
                 data:Optional[dict[str, list[str]]]=None, /,
                 runner:Optional[Callable[[str], Any]]=None):
        super().__init__(data)
        self.runner = runner

    #------------------------------------|    Dirty state

    def get_dirty(self, node:str) -> bool:
        """
        Override this to determine, based on external data, whether a node
        should be recooked (this will involve looking at upstream nodes too).
        """
        raise NotImplementedError

    def dirty_nodes(self) -> Iterator[str]:
        for node in self.nodes():
            if self.get_dirty(node):
                yield node

    #------------------------------------|    Sequence calcs

    def sequence_to(self, target_node:str, dirty:bool=True) -> list[str]:
        out = super().sequence_to(target_node)
        if dirty:
            out = [node for node in out if self.get_dirty(node)]
        return out

    def sequence(self, dirty:bool=True) -> list[str]:
        out = list(
            without_duplicates(
                chain.from_iterable(
                    self.sequence_to(tip, False) for tip in self.tips()
                )
            )
        )
        if dirty:
            out = [node for node in out if self.get_dirty(node)]
        return out

    #------------------------------------|    Runs

    def _run_node(self, node:str) -> Any:
        if self.runner is None:
            return_value = None
        else:
            return_value = self.runner(node)

        return return_value

    def run_to(self,
               target_node:str,
               dirty:bool=True) -> Iterator[tuple[str, Any]]:
        for node in self.sequence_to(target_node, dirty):
            yield node, self._run_node(node)

    def run(self,
            dirty:bool=True) -> Iterator[tuple[str, Any]]:
        for node in self.sequence(dirty):
            yield node, self._run_node(node)

    #------------------------------------|    Copying

    def copy(self) -> 'DagBase':
        out = super().copy()
        out.runner = self.runner
        return out


class DagTestRunner(DagRunner):
    """
    Testing variant of :class:`DagRunner` that doesn't take a ``runner`` and
    implements``get_dirty`` to work off of an internal lookup.
    """
    #------------------------------------|    Init

    def __init__(self, data:Optional[dict[str, list[str]]]=None):
        super().__init__(data)
        self._dirties = {}

    #------------------------------------|    Dirty

    def get_dirty(self, node:str) -> bool:
        return (self._dirties.get(node, True)
                or any((self._dirties.get(us_node, True)
                        for us_node in self.upstream(node))))

    def set_dirty(self, node:str, state:bool):
        self._dirties[node] = state

    def set_dirty_all(self, state:bool):
        for node in self.nodes():
            self._dirties[node] = state

    def _run_node(self, node:str) -> Any:
        self._dirties[node] = False

    #------------------------------------|    Copying

    def copy(self) -> 'DagBase':
        out = super().copy()
        out._dirties = self._dirties.copy()
        return out