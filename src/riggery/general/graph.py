"""
Todo:
Create a context where upstream() / downstream() are cached
(memoized), e.g. when called within the sequence() calculations. Look over
recursion carefully so that all intermediate calls are cached accordingly.
"""

from itertools import pairwise
from .iterables import without_duplicates
from typing import Optional, Iterator, Callable, Iterable, Literal
import json

class CycleError(Exception): ...

class Dag:
    """
    Data model (Python)
    -------------------
    {
        <name:str>: {'dirty':bool, 'inputs': list[str], 'tool': Callable}
    }

    How to use
    ----------

    1.  Instantiate: `graph = GraphData()`
    2.  Add some nodes: `graph.create_node('build_puppet', 'bind_geometry')`
    3.  Define connections using the provided methods:
        `graph.connect('build_puppet', 'bind_geometry')`
    4.  Use :meth:`sequence` to get a flat build sequence
    5.  Subclass this class and override :meth:`_set_dirty` and
        :meth:`_get_dirty` to implement external 'dirty' tracking (e.g. in
        sidecar files)
    6.  Use :meth:`set_tool` to embed actual callables into the graph so that,
        when you call :meth:`cook`, they get run and the dirty states are set
        accordingly.
    """
    #--------------------------------------|    Constructor(s)

    @classmethod
    def from_shorthand(cls, items:Iterable[Iterable[str]|str]):
        """
        :param items: An iterable of iterables or single strings (for node
            names); where there are sub-iterables, they will be used to define
            sequential connections between nodes
        """
        items = [item if isinstance(item, str) else list(item)
                 for item in items]

        node_names = []
        connections = []

        for item in items:
            if isinstance(item, str):
                node_names.append(item)
            else:
                node_names.extend(item)
                connections.append(item)

        graph = cls()
        graph.create_node(*without_duplicates(node_names))

        for connection in connections:
            if len(connection) > 1:
                graph.connect(*connection)

        return graph

    #--------------------------------------|    Init

    def __init__(self, data:Optional[dict]=None, /):
        if data is None:
            self._data = {}
        else:
            self._data = data

    #--------------------------------------|    Enumeration

    def names(self) -> Iterator[str]:
        yield from self._data.keys()

    def specs(self) -> Iterator[dict]:
        yield from self._data.values()

    def items(self) -> Iterator[tuple[str, dict]]:
        yield from self._data.items()

    def __getitem__(self, name:str):
        return self._data[name]

    def __contains__(self, name:str):
        return name in self._data

    def __iter__(self):
        return iter(self.names())

    #--------------------------------------|    Create nodes

    def create_node(self, *names:str):
        for name in names:
            if name in self._data:
                raise KeyError("name '{}' already in use".format(name))

        for name in names:
            self._data[name] = {}

    #--------------------------------------|    Tools

    def set_tool(self, node:str, tool:Optional[Callable]):
        data = self[node]

        if tool is None:
            try:
                del(data['tool'])
            except KeyError:
                pass
        else:
            if callable(tool):
                data['tool'] = tool
            else:
                raise TypeError("expected a callable")

    def get_tool(self, node:str) -> Optional[Callable]:
        return self[node].get('tool')

    #--------------------------------------|    Inspect topology

    def _check_name(self, name:str):
        """:raises KeyError:"""
        if name not in self._data:
            raise KeyError("name not found: '{}'".format(name))
        return name

    def _get_topology(self) -> dict[str, list[str]]:
        """
        :return: A dictionary of {node:inputs}, for backup purposes.
        """
        return {name: list(spec.get('inputs', []))
                for name, spec in self.items()}

    def inputs(self, name:str) -> Iterator[str]:
        """Yields nodes that connect into *name*."""
        yield from self[name].get('inputs', [])

    def upstream(self, name:str, visited:Optional[set]=None) -> Iterator[str]:
        """Yields all nodes upstream of *name*, proximal nodes first."""

        if visited is None:
            visited = set()

        for us_node in self.inputs(name):
            if us_node not in visited:
                visited.add(us_node)
                yield us_node
                yield from self.upstream(us_node, visited)

    def outputs(self, name:str) -> Iterator[str]:
        """Yields nodes that *name* connects into."""
        self._check_name(name)

        for this_name, this_spec in self.items():
            if name == this_name:
                continue
            if name in this_spec.get('inputs', []):
                yield this_name

    def downstream(self,
                   name:str,
                   visited:Optional[set]=None) -> Iterator[str]:
        """Yields all nodes downstream of *name*, proximal nodes first."""
        if visited is None:
            visited = set()

        for output in self.outputs(name):
            if output not in visited:
                visited.add(output)
                yield output
                yield from self.downstream(output, visited)

    def roots(self) -> Iterator[str]:
        """Yields all nodes in the graph with no inputs."""
        for name in self.names():
            if not list(self.inputs(name)):
                yield name

    def tips(self) -> Iterator[str]:
        """Yields all nodes in the graph with no outputs."""
        for name in self.names():
            if not list(self.outputs(name)):
                yield name

    #--------------------------------------|    Edit topology

    def _set_topology(self, topology:dict):
        for name, spec in self._data.items():
            try:
                new_inputs = topology[name]
            except KeyError:
                continue
            if new_inputs:
                spec.setdefault('inputs', [])[:] = new_inputs
            else:
                try:
                    del(spec['inputs'])
                except KeyError:
                    continue

    def connect(self, *node_sequence:str) -> int:
        """
        Sets each node in the sequence as an input for the next one.

        :param *node_sequence: the nodes to connect
        :raises CycleError:
        :return: Number of new connections made.
        """
        backup = self._get_topology()

        node_sequence = list(node_sequence)

        if len(node_sequence) < 2:
            raise Exception("need at least two nodes")

        for node in node_sequence:
            self._check_name(node)

        count = 0

        try:
            for src_node, dest_node in pairwise(node_sequence):
                if src_node == dest_node or dest_node in self.upstream(src_node):
                    raise CycleError

                dest_data = self._data[dest_node]
                if src_node in dest_data.get('inputs', []):
                    continue
                dest_data.setdefault('inputs', []).append(src_node)
                count += 1

        except CycleError as e:
            self._set_topology(backup)
            raise e

        return count

    #--------------------------------------|    Exec

    def _get_dirty(self, node:str) -> bool:
        """
        Override this method if you want the state to be stored externally.
        """
        return self[node].get('dirty', True)

    def get_dirty(self, node:str) -> bool:
        """
        This has some redundancy baked-in (will traverse upstream nodes to
        make sure none are dirty).
        """
        if self._get_dirty(node):
            return True

        for us_node in self.upstream(node):
            if self._get_dirty(us_node):
                return True

        return False

    def _set_dirty(self, node:str, state:bool):
        """
        Override this method if you want the state to be stored externally.
        """
        self[node]['dirty'] = bool(state)

    def set_dirty(self, node:str, state:bool):
        """
        :param node: the node to tag
        :param state: if this is True, then both *node* and all nodes
            downstream of it will be marked as dirty; otherwise, both *node*
            and all nodes *upstream* of it will be marked as clean
        """
        if state:
            self._set_dirty(node, True)
            for ds_node in self.downstream(node):
                self._set_dirty(ds_node, True)
        else:
            self._set_dirty(node, False)
            for us_node in self.upstream(node):
                self._set_dirty(us_node, False)

    def set_dirty_all(self, state:bool):
        """Marks all nodes in the graph."""
        for name in self.names():
            self._set_dirty(name, state)

    def _clean_worklist(self,
                        *nodes:str,
                        mode:Literal[0, 1, 2]=0) -> list[str]:
        """
        :param \*nodes: the user worklist to clean up
        :param mode: 1: remove any nodes in the list that are upstream of any
            other nodes in the list; 2: remove any nodes in the list that are
            downstream of any other nodes in the list; 0: don't prune for
            implicit membership; defaults to 0
        """
        nodes = list(without_duplicates(nodes))

        if mode == 1:
            _nodes = []
            for node in nodes:
                siblings = [x for x in nodes if x != node]
                if any(node in self.upstream(sibling)
                       for sibling in siblings):
                    continue
                _nodes.append(node)
            return _nodes

        if mode == 2:
            _nodes = []
            for node in nodes:
                siblings = [x for x in nodes if x != node]
                if any(node in self.downstream(sibling)
                       for sibling in siblings):
                    continue
                _nodes.append(node)
            return _nodes

        return nodes

    def sequence_from(self, *start_nodes:str) -> list[str]:
        """
        :return: Every node that would have to be built if *start_nodes* were
            marked dirty.
        """
        start_nodes = self._clean_worklist(*start_nodes, mode=2)

        if not start_nodes:
            raise ValueError('no start nodes')

        visited = set()
        out = []

        for node in start_nodes:
            out.append(node)
            for ds_node in self.downstream(node, visited):
                out.append(ds_node)

        return out

    def sequence_to(self, *end_nodes:str, sparse:bool=True) -> list[str]:
        """
        :param sparse: don't build anything that isn't marked dirty; defaults
            to True
        :return: If *sparse* is True, only the nodes that will have to be
            built to 'clean' the end nodes, in order. Otherwise, all nodes
            upstream of, and including, the end nodes, in build order.
        """
        end_nodes = self._clean_worklist(*end_nodes, mode=1)

        if not end_nodes:
            raise ValueError('no end nodes')

        def chase(node):
            if (not sparse) or self.get_dirty(node):
                yield node
                for input_node in self.inputs(node):
                    yield from chase(input_node)

        out = []

        for end_node in end_nodes:
            this_sequence = reversed(list(chase(end_node)))
            for node in this_sequence:
                if node not in out:
                    out.append(node)

        return out

    def sequence(self, sparse:bool=True) -> list[str]:
        """
        :param sparse: don't build anything that isn't marked dirty; defaults
            to True
        :return: If *sparse* is True, only the nodes that will have to be
            built to 'clean' the graph, in order. Otherwise, all nodes, in
            order.
        """
        return self.sequence_to(*self.tips(), sparse=sparse)

    def cook_nodes(self, *nodes:str) -> Iterator[str]:
        """
        Prepare a build sequence using one of the 'sequence' methods, then
        iterate over this generator.
        """
        nodes = self._clean_worklist(*nodes)

        for node in nodes:
            tool = self.get_tool(node)

            if tool is not None:
                tool()
            self._set_dirty(node, False)

            for output in self.outputs(node):
                self.set_dirty(output, True)

            yield node

    #--------------------------------------|    Serialization

    def json(self) -> str:
        """Note that any embedded tools will be discarded."""
        data = []
        keys_to_include = ('inputs', 'dirty')

        for name, spec in self._data.items():
            this_simplified_spec = {}
            for key in keys_to_include:
                try:
                    this_simplified_spec[key] = spec[key]
                except KeyError:
                    continue
            data.append((name, this_simplified_spec))

        return json.dumps(data, indent=4)

    @classmethod
    def from_json(cls, json_data:str) -> 'Dag':
        return cls({k: v for k, v in json.loads(json_data)})

    #--------------------------------------|    Repr

    def __repr__(self) -> str:
        return "{}({})".format(type(self).__name__, repr(self._data))