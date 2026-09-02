from itertools import pairwise
from .iterables import without_duplicates
from typing import Optional, Iterator, Callable

import json

class CycleError(Exception): ...

class DagData:
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
        :meth:`get_dirty` to implement external 'dirty' tracking (e.g. in
        sidecar files)
    6.  Use :meth:`set_tool` to embed actual callables into the graph so that,
        when you call :meth:`cook`, they get run and the dirty states are set
        accordingly.
    """
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
        for name, spec in self.items():
            if not list(self.inputs(name)):
                yield name

    def tips(self) -> Iterator[str]:
        """Yields all nodes in the graph with no outputs."""
        for name, spec in self.items():
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

    def get_dirty(self, node:str) -> bool:
        """
        If no value is embedded in the data, the default will always be True.
        Override this method if you want the state to be derived externally.
        """
        return self[node].get('dirty', True)

    def _set_dirty(self, node:str, state:bool):
        """
        Non-propagating implementation. Override to implement external
        tagging.
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

    def sequence(self,
                 *end_nodes:str,
                 force:bool=False) -> list[str]:
        """
        :param \*end_nodes: if omitted, defaults to all 'tip' nodes in the graph
        :param force: ignore dirty states and return the full dependency stack;
            defaults to False
        :return: The sequence of nodes that would have to be cooked to make
            all the end nodes 'clean'.
        """
        if end_nodes:
            _end_nodes = list(without_duplicates(end_nodes))
            end_nodes = []

            for end_node in _end_nodes:
                siblings = (node for node in _end_nodes if node != end_node)
                if any(end_node in self.upstream(sibling)
                       for sibling in siblings):
                    continue
                end_nodes.append(end_node)
        else:
            end_nodes = list(self.tips())

        def chase(node):
            if force or self.get_dirty(node):
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

    def cook(self, *end_nodes:str, force:bool=False):
        for node in self.sequence(*end_nodes, force=force):
            spec = self[node]
            tool = spec.get('tool')
            if tool is not None:
                tool()
            self._set_dirty(node, False)
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
    def from_json(cls, json_data:str) -> 'DagData':
        return cls({k: v for k, v in json.loads(json_data)})

    #--------------------------------------|    Repr

    def __repr__(self) -> str:
        return "{}({})".format(type(self).__name__, repr(self._data))