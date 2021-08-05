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

  def testSearch(self):
    device = {
        'device_serial': 'device_0',
        'lab_name': 'lab-name-1',
        'hostname': 'host_0',
        'run_target': 'run_target',
        'product': 'product',
        'state': 'Available',
        'timestamp': '2015-10-09T00:00:00',
        'battery_level': '100',
        'hidden': False,
        'cluster': 'free',
        'host_group': 'host_group_01',
        'pools': ['pool_01'],
        'device_type': 'PHYSICAL',
        'test_harness': 'tradefed'
    }
    response = {
        'took': 5,
        'timed_out': False,
        '_shards': {
            'total': 1,
            'successful': 1,
            'skipped': 0,
            'failed': 0
        },
        'hits': {
            'total': {
                'value': 20,
                'relation': 'eq'
            },
            'max_score':
                1.3862942,
            'hits': [{
                '_index': 'devices',
                '_type': '_doc',
                '_id': '0',
                '_score': 1.3862942,
                '_source': device
            },]
        }
    }
    self.mock_client.search = mock.MagicMock(return_value=response)
    elastic_query = {
        'size': 10,
        'query': {
            'bool': {
                'must': [{
                    'bool': {
                        'should': [{
                            'term': {
                                'lab_name.keyword': 'alab'
                            }
                        }]
                    }
                }]
            }
        }
    }
    results = self.elasticsearch_client.Search('devices', elastic_query)
    self.mock_client.search.assert_called_once_with(
        index='devices', body=elastic_query)
    self.assertEqual(results, [device])


if __name__ == '__main__':
  unittest.main()
