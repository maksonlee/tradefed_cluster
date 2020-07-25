"""Tests for google3.third_party.py.tradefed_cluster.util.datastore_emulator."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import unittest

from tradefed_cluster.util import datastore_emulator


class DatastoreEmulatorTest(unittest.TestCase):

  def testFactoryDoesNotRaiseErrors(self):
    datastore_emulator.DatastoreEmulatorFactory()


if __name__ == '__main__':
  unittest.main()
