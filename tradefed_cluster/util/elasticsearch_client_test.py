"""Tests for elasticearch_client."""
import unittest
from unittest import mock

from tradefed_cluster.util import elasticsearch_client


class ElasticsearchClientTest(unittest.TestCase):

  def setUp(self):
    super(ElasticsearchClientTest, self).setUp()
    self.mock_client = mock.MagicMock()
    self.elasticsearch_client = elasticsearch_client.ElasticsearchClient()
    self.elasticsearch_client._GetEsClient = mock.MagicMock(
        return_value=self.mock_client)

  def testGetDoc(self):
    self.mock_client.get = mock.MagicMock()
    self.elasticsearch_client.GetDoc('devices', 'device_0')
    self.mock_client.get.assert_called_once_with(index='devices', id='device_0')

  def testUpsertDoc(self):
    self.mock_client.index = mock.MagicMock()
    device_0 = {
        'clusters': 'free',
        'hostname': 'host_0',
        'device_serial': 'device_0'
    }
    self.elasticsearch_client.UpsertDoc('devices', 'device_0', device_0)
    self.mock_client.index.assert_called_once_with(
        'devices', id='device_0', body=device_0)


if __name__ == '__main__':
  unittest.main()
