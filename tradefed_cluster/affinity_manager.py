"""A module for command task/device affinity management."""

import logging
import typing

from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster.util import ndb_shim as ndb


def _UpdateAffinityStatus(
    affinity_tag: str,
    device_count_delta: int = 0,
    task_count_delta: int = 0,
    needed_device_count_delta: int = 0):
  """Updates an affinity status record.

  This function must be called within a transaction to update device/task
  affinity infos.

  Args:
    affinity_tag: an affinity tag.
    device_count_delta: a change for device_count field
    task_count_delta: a change for task_count_field
    needed_device_count_delta: a change for needed_device_count field
  """
  key = ndb.Key(
      datastore_entities.AffinityStatus,
      affinity_tag,
      namespace=common.NAMESPACE)
  status = key.get()
  if not status:
    status = datastore_entities.AffinityStatus(
        key=key, affinity_tag=affinity_tag)
  status.device_count += device_count_delta
  status.task_count += task_count_delta
  status.needed_device_count += needed_device_count_delta
  status.put()
  logging.info('Affinity status updated: %s', status)


@ndb.transactional(xg=True)
def SetDeviceAffinity(device_serial: str, affinity_tag: str):
  """Set an affinity tag for a device.

  Args:
    device_serial: a device serial.
    affinity_tag: an affinity tag.
  """
  if not affinity_tag:
    raise ValueError('affnity_tag cannot be None or empty')
  key = ndb.Key(
      datastore_entities.DeviceAffinityInfo,
      device_serial,
      namespace=common.NAMESPACE)
  info = key.get()
  if not info:
    info = datastore_entities.DeviceAffinityInfo(key=key)
    info.device_serial = device_serial
    info.affinity_tag = affinity_tag
    info.put()
    _UpdateAffinityStatus(info.affinity_tag, device_count_delta=1)
    return
  if info.affinity_tag == affinity_tag:
    return
  _UpdateAffinityStatus(info.affinity_tag, device_count_delta=-1)
  _UpdateAffinityStatus(affinity_tag, device_count_delta=1)
  info.affinity_tag = affinity_tag
  info.put()
  logging.info('Device affinity set: %s', info)


@ndb.transactional(xg=True)
def ResetDeviceAffinity(
    device_serial: str, only_if_excess: bool = False) -> bool:
  """Reset a device's affinity info.

  Args:
    device_serial: a device serial.
    only_if_excess: check the affinity status and reset only if it is an excess
        device.
  Returns:
    True if the device affinity was reset. Otherwise False.
  """
  key = ndb.Key(
      datastore_entities.DeviceAffinityInfo,
      device_serial,
      namespace=common.NAMESPACE)
  info = key.get()
  if not info:
    return True
  if only_if_excess:
    key = ndb.Key(
        datastore_entities.AffinityStatus,
        info.affinity_tag,
        namespace=common.NAMESPACE)
    status = key.get()
    if status and status.device_count <= status.needed_device_count:
      return False
  _UpdateAffinityStatus(info.affinity_tag, device_count_delta=-1)
  key.delete()
  logging.info('Device affinity reset: device_serial=%s', device_serial)
  return True


def GetDeviceAffinityInfos(
    device_serials: typing.List[str]
    ) -> typing.List[datastore_entities.DeviceAffinityInfo]:
  """Return affinity infos of one or more devices.

  Args:
    device_serials: a list of device serials.
  Returns:
    a list of device affinity infos.
  """
  keys = [
      ndb.Key(            datastore_entities.DeviceAffinityInfo,
          device_serial,
          namespace=common.NAMESPACE) for device_serial in device_serials
  ]
  return ndb.get_multi(keys)


@ndb.transactional(xg=True)
def SetTaskAffinity(task_id: str, affinity_tag: str, needed_device_count: int):
  """Set an affinity tag for a device.

  Args:
    task_id: a task ID.
    affinity_tag: an affinity tag.
    needed_device_count: a needed device count.
  """
  if not affinity_tag:
    raise ValueError('affnity_tag cannot be None or empty')
  key = ndb.Key(
      datastore_entities.TaskAffinityInfo, task_id, namespace=common.NAMESPACE)
  info = key.get()
  if not info:
    info = datastore_entities.TaskAffinityInfo(
        key=key,
        task_id=task_id,
        affinity_tag=affinity_tag,
        needed_device_count=needed_device_count)
    info.put()
    _UpdateAffinityStatus(
        info.affinity_tag,
        task_count_delta=1,
        needed_device_count_delta=needed_device_count)
    return
  if info.affinity_tag == affinity_tag:
    return
  _UpdateAffinityStatus(
      info.affinity_tag,
      task_count_delta=-1,
      needed_device_count_delta=-info.needed_device_count)
  _UpdateAffinityStatus(
      affinity_tag,
      task_count_delta=1,
      needed_device_count_delta=needed_device_count)
  info.affinity_tag = affinity_tag
  info.needed_device_count = needed_device_count
  info.put()
  logging.info('Task affinity set: %s', info)


@ndb.transactional(xg=True)
def ResetTaskAffinity(task_id: str):
  """Reset a task's affinity.

  Args:
    task_id: a task ID.
  """
  key = ndb.Key(
      datastore_entities.TaskAffinityInfo,
      task_id,
      namespace=common.NAMESPACE)
  info = key.get()
  if not info:
    return
  _UpdateAffinityStatus(
      info.affinity_tag,
      task_count_delta=-1,
      needed_device_count_delta=-info.needed_device_count)
  key.delete()
  logging.info('Task affinity reset: task_id=%s', task_id)


def GetTaskAffinityInfo(task_id: str) -> datastore_entities.TaskAffinityInfo:
  """Return a task's affinity info.

  Args:
    task_id: a task ID.
  Returns:
    task affinity info.
  """
  return GetTaskAffinityInfos([task_id])[0]


def GetTaskAffinityInfos(
    task_ids: typing.List[str]
    ) -> typing.List[datastore_entities.TaskAffinityInfo]:
  """Return affinity infos of one or more tasks.

  Args:
    task_ids: a list of task IDs.
  Returns:
    a list of task affinity infos.
  """
  keys = [
      ndb.Key(            datastore_entities.TaskAffinityInfo,
          task_id,
          namespace=common.NAMESPACE) for task_id in task_ids
  ]
  return ndb.get_multi(keys)


def GetAffinityStatus(affinity_tag: str) -> datastore_entities.AffinityStatus:
  """Return the status of an affinity tag.

  Args:
    affinity_tag: an affinity tag.
  Returns:
    an affinity status.
  """
  return GetAffinityStatuses([affinity_tag])[0]


def GetAffinityStatuses(
    affinity_tags: typing.List[str]
    ) -> typing.List[datastore_entities.AffinityStatus]:
  """Return the statuses of affinity tags.

  Args:
    affinity_tags: a list of affinity tags.
  Returns:
    the affinity statuses.
  """
  keys = [
      ndb.Key(            datastore_entities.AffinityStatus,
          affinity_tag,
          namespace=common.NAMESPACE) for affinity_tag in affinity_tags
  ]
  return ndb.get_multi(keys)


