#Test bindery performance

# Resources:
#   http://www.skymind.com/~ocrow/python_string/
#   http://code.activestate.com/recipes/286222/
#   http://www.oreillynet.com/onlamp/blog/2007/09/pymotw_timeit.html

import unittest
import os
from cStringIO import StringIO
import commands, os
import itertools

from timeit import Timer

from amara.lib import testsupport

import amara
from amara import bindery

SCALE = 100
TIMER_COUNT = 2000

class Test_increment_over_core_tree(unittest.TestCase):
    def setUp(self):
        self.bigdoc1 = ["<A>"]
        self.bigdoc1.extend(["<B/>"]*SCALE)
        self.bigdoc1.extend(["</A>"])
        self.bigdoc1 = ''.join(self.bigdoc1)
        #len(self.bigdoc1) is 4007 for SCALE = 1000
        self.doc = amara.parse(self.bigdoc1)
        t0 = Timer('amara.parse(doc)', 'import amara; doc = %r'%(self.bigdoc1))
        #self.base_tree_time = min(t0.repeat(3))
        self.base_tree_time = t0.timeit(TIMER_COUNT)
        print self.base_tree_time
        return

    def test_bindery_parse(self):
        #self.assert_(diff/SCALE < 0.01)
        t1 = Timer('bindery.parse(doc)', 'from amara import bindery; doc = %r'%(self.bigdoc1))
        #t = min(t1.repeat(3))
        t = t1.timeit(TIMER_COUNT)
        print t, (t - self.base_tree_time)/self.base_tree_time
        #self.assert_(diff/SCALE < 0.01)
        self.assert_(t < 3)
        return


if __name__ == '__main__':
    testsupport.test_main()
