########################################################################
# amara/bindery/__init__.py

"""
Extra friendly XML node API for Python
"""

import nodes
from amara import Error

def parse(obj, uri=None, entity_factory=None, standalone=False, validate=False):
    from amara import tree
    if not entity_factory:
        entity_factory = nodes.entity_base
    return tree.parse(obj, uri, entity_factory=entity_factory, standalone=standalone, validate=validate)


constraint = nodes.constraint

class BinderyError(Error):
    CONSTRAINT_VIOLATION = 1


#FIXME: Use proper L10N (gettext)
def _(t): return t

