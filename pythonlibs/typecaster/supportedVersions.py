"""

Submodule for checking what versions of nodes the current python module explicitly supports.

"""


from __future__ import annotations
import hou


# Due to the complex nature of Typecaster and it being feasable for typecaster's Python
# modules to be out of step with the HDA's being used, the main Typecaster Font node
# will surface a warning if it isn't used with the correct version. This is done by
# checking if the HDA being used is explicitly listed below.
# Right now, this is done using a message parameter which runs get_compatible_warning().
# Ideally, this would be a node-level warning, but there aren't many reliable ways to do
# this that get carried to the top-level node.
SUPPORTED_VERSIONS = {
    'typecaster_font' : {
        '1.0',
    },
}


def check_node_compatible(node:hou.OpNode):
    """Check if the current node is directly listed as being compatible with the current Typecaster python module

    Args:
        node (hou.OpNode): Node to check

    Returns:
        bool: Returns True if the node's name and version is explicitly supported, otherwise returns False.
    """
    nc = node.type().nameComponents()
    name = nc[2]
    if name in SUPPORTED_VERSIONS:
        version = nc[3]
        if version in SUPPORTED_VERSIONS[name]:
            return True
    return False


# As of writing, this is the primary function directly used by Typecaster Font to warn
# about version mismatches. This function's name should NEVER be changed due to backwards
# compatibility being an absolute requirement for this system to work.
def get_compatible_warning(node:hou.OpNode):
    """If applicable, return a warning message to be used in typecaster_font's interface.

    Args:
        node (hou.OpNode): Node to check

    Returns:
        str: Warning message (if any).
    """    
    if check_node_compatible(node):
        return ''
    else:
        return f"""WARNING:\nThis asset ({node.type().name()}) is not directly listed as being supported by current version of Typecaster's python module.\nWhile the node may still function, there could be unexpected or different results.\nPlease update Typecaster or ensure that it's python libraries are on the intended version."""
