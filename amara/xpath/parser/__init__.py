from amara.xpath import XPathError
from amara.xparh.parser import _xpathparser

__all__ = ['xpathparser', 'parse']

class xpathparser(_xpathparser.parser):

    _parse = _xpathparser.parser

    def parse(self, expr):
        """Parses the string `expr` into an AST"""
        try:
            return self._parse(expr)
        except _xpathparser.error, error:
            raise XPathError(XPathError.SYNTAX, line=error.lineno, 
                             column=error.offset, message=error.msg)


parse = xpathparser().parse

if __name__ == '__main__':
    _xpathparser.console()