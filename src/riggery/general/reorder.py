from typing import Any, Iterable, Optional, Union

class Reorder(list):
    """
    List subclass with convenience reordering methods. Members must be hashable
    and unique. If in doubt, assign to unique keys in a dict, run reordering
    operations on the keys, and then re-extract the values.
    """
    def _check_members(self, members):
        """
        :raises ValueError: Non-members.
        :raises ValueError: Duplicate members.
        :raises TypeError: Unhashable type(s).
        """
        members = list(members)
        try:
            _members = set(members)
        except TypeError:
            raise TypeError("Unhashable member types.")
        if len(_members) < len(members):
            raise ValueError("Duplicate members.")

        nonmembers = [member for member in members if member not in self]
        if nonmembers:
            raise ValueError("Non-member(s): {}".format(', '.join(nonmembers)))
        return members

    def in_order(self, members:Iterable) -> list[Any]:
        """
        :return: A copy of *members*, in the order they appear within this list
            (ignoring interjecting members).
        """
        members = self._check_members(members)
        foreign = [member for member in members if member not in self]
        if foreign:
            raise ValueError("Non-member(s): {}".format(', '.join(foreign)))
        return [x for x in self if x in members]

    def roll_index(self, index:int) -> int:
        """
        :param index: the index to roll
        :return: The index, but rolled so that it falls within the list's actual
            index range.
        """
        return index % len(self)

    def clamp_index(self, index:int) -> int:
        """
        :param index: the index to clamp
        :return: The index, but clamped between 0 -> len(self)-1.
        """
        return max(0, min(index, len(self)-1))

    def assign(self, members:Iterable[Any], indices:list[int]) -> None:
        """
        In-place operation. Reassigns *members* to the specified indices, and
        flows other members around them.

        :param members: the members to reassign
        :param indices: the new indices for *members*
        """
        members = self._check_members(members)
        indices = [self.roll_index(index) for index in indices]

        index_list = indices + [index for index
                                in range(len(self)) if index not in indices]

        members_list = members + [member for member
                                  in self if member not in members]
        for index, member in zip(index_list, members_list):
            self[index] = member

    def shift(self, members, offset:int, roll:bool=False) -> None:
        """
        In-place operation. Shifts *members* by a given offset.

        :param members: the members to shift
        :param offset: the shifting step; the method will do nothing if this is
            set to 0
        :param roll: if this is True, the specified members will roll back into
            range if they overshoot the list bounds; if it's False, they will
            instead 'bunch up'; defaults to False
        """
        members = self.in_order(self._check_members(members))

        if offset:
            if roll:
                indices = [self.roll_index(self.index(member) + offset)
                           for member in members]
                members = members + [member for member
                                     in self if member not in members]
                self.assign(members, indices)
            else:
                if offset > 0:
                    maxindex = len(self)-1
                    indices = []

                    for member in reversed(members):
                        old = self.index(member)
                        new = old + offset
                        if new > maxindex:
                            new = maxindex
                            maxindex -= 1
                        indices.append(new)
                    self.assign(members, reversed(indices))

                else:
                    minindex = 0
                    indices = []

                    for member in members:
                        old = self.index(member)
                        new = old + offset
                        if new < minindex:
                            new = minindex
                            minindex += 1
                        indices.append(new)
                    self.assign(members, indices)

    def copy(self) -> 'Reorder':
        """
        Overrides :meth:`list.copy` to return a :class:`Reorder` instance.
        """
        return type(self)(super().copy())