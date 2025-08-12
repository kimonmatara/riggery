"""Misc utilities for Maya undo management."""

import maya.cmds as m

class InfiniteUndo:
    """
    Context manager. Forces an infinite undo the the specified block. Used
    for attribute reordering etc.
    """
    def __enter__(self):
        self._prevState = m.undoInfo(q=True, state=True)
        self._prevInf = m.undoInfo(q=True, infinity=True)

        if not self._prevState:
            m.undoInfo(state=True)

        if not self._prevInf:
            m.undoInfo(infinity=True)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._prevInf:
            m.undoInfo(infinity=False)

        if not self._prevState:
            m.undoInfo(state=False)

        return False

class UndoChunk:
    """
    Context manager. Defines an undo chunk.
    """
    def __enter__(self):
        m.undoInfo(openChunk=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        m.undoInfo(closeChunk=True)
        return False