from itertools import pairwise, chain
from .iterables import without_duplicates
from typing import Optional, Iterator, Callable

import json

class CycleError(Exception): ...

class DagData:
    """
    Data model (Python)
    {
        <name:str>: {'dirty':bool, 'inputs': list[str], 'tool': Callable}
    }
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
            if name in self.names():
                raise KeyError("name '{}' already in use".format(name))

        for name in names:
            self._data[name] = {'dirty': True}

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
        return {name: spec.get('inputs') for name, spec in self.items()}

    def inputs(self, name:str) -> Iterator[str]:
        """Yields nodes that connect into *name*."""
        yield from self[name].get('inputs', [])

    def upstream(self, name:str) -> Iterator[str]:
        """Yields all nodes upstream of *name*, proximal nodes first."""
        for input in self.inputs(name):
            yield input
            yield from self.upstream(input)

    def outputs(self, name:str) -> Iterator[str]:
        """Yields nodes that *name* connects into."""
        self._check_name(name)

        for this_name, this_spec in self.items():
            if name == this_name:
                continue
            if name in this_spec.get('inputs', []):
                yield this_name

    def downstream(self, name:str) -> Iterator[str]:
        """Yields all nodes downstream of *name*, proximal nodes first."""
        self._check_name(name)

        for output in self.outputs(name):
            yield output
            yield from self.downstream(output)

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

        if end_nodes:
            _end_nodes = list(without_duplicates(end_nodes))
            end_nodes = []

            for end_node in _end_nodes:
                siblings = (node for node in end_nodes if node != end_node)
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

    def run(self, *end_nodes:str, force:bool=False):
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

        for name, spec in self._data.items():
            data.append(name, {k:spec[k] for k in ('inputs', 'dirty')})

        return json.dumps(data, indent=4)

    @classmethod
    def from_json(cls, json_data:str) -> 'Graph':
        return cls({k: v for k, v in json.loads(json_data)})

    #--------------------------------------|    Repr

    def __repr__(self) -> str:
        return "{}({})".format(type(self).__name__, repr(self._data))


def test():
    graph = DagData()
    graph.create_node('build_puppet')
    graph.create_node('extract_unified_skel')
    graph.create_node('import_geo_and_bind_to_unified_skel')
    graph.create_node('import_geo_and_bind_to_puppet')
    graph.create_node('deform_only_rig')
    graph.create_node('full_rig')

    graph.connect('build_puppet',
                  'extract_unified_skel',
                  'import_geo_and_bind_to_unified_skel',
                  'deform_only_rig')

    graph.connect('build_puppet',
                  'import_geo_and_bind_to_puppet',
                  'full_rig')

    graph.clean_all()
    graph.dirty('extract_unified_skel')

    for x in graph.run():
        print(x)