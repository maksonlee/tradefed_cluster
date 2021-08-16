"""Unified lab config parser."""
from ansible.inventory import data as inventory_data
from ansible.inventory import helpers
from ansible.plugins.inventory import ini

_ROOT_GROUP = 'all'
_UNGROUPED_GROUP = 'ungrouped'


def Parse(file_path):
  """Parse unified lab config.

  Args:
    file_path: file path to the config.
  Returns:
    a UnifiedLabConfig object.
  """
  data = inventory_data.InventoryData()
  ini.InventoryModule().parse(data, None, file_path)
  return UnifiedLabConfig(data)


class _Group(object):
  """A wrap around ansible.inventory.Group.

  So we only expose needed interfaces.
  """

  def __init__(self, inventory_group):
    self._inventory_group = inventory_group

  @property
  def name(self):
    """name of the group."""
    return self._inventory_group.get_name()

  @property
  def direct_vars(self):
    """Vars defined directly in the group."""
    return self._inventory_group.get_vars()


class _Host(object):
  """A wrap around ansible.inventory.Host.

  So we only expose needed interfaces.
  """

  def __init__(self, inventory_host, root_group):
    self._inventory_host = inventory_host
    self._root_group = root_group
    self._inventory_groups = None

  @property
  def name(self):
    """Name of the host."""
    return self._inventory_host.get_name()

  @property
  def groups(self):
    """Groups the host belong to.

    The groups are sorted from general to specific.

    Returns:
      a list of _Group objects.
    """
    if not self._inventory_groups:
      self._inventory_groups = (self._inventory_host.get_groups() +
                                [self._root_group])
      self._inventory_groups = helpers.sort_groups(self._inventory_groups)
    return [_Group(g) for g in self._inventory_groups]

  @property
  def direct_vars(self):
    """Vars directly defined for the host."""
    return self._inventory_host.get_vars()

  def GetVar(self, key):
    """Get var for a key, will check parent groups as well."""
    if key in self._inventory_host.vars:
      return self._inventory_host.vars[key]
    for g in reversed(self.groups):
      if key in g.direct_vars:
        return g.direct_vars[key]
    return None


class UnifiedLabConfig(object):
  """A unified lab config provides APIs to query config."""

  def __init__(self, data):
    """Initialilzed unified lab config."""
    self._data = data

  def ListGlobalVars(self):
    """List global vars."""
    return self._data.groups[_ROOT_GROUP].get_vars()

  def GetGlobalVar(self, key):
    """Get value for a key in global var."""
    return self._data.groups[_ROOT_GROUP].vars.get(key)

  def ListGroups(self):
    """List groups."""
    return [_Group(g) for g in self._data.groups.values()]

  def GetGroup(self, group_name):
    """Get a group."""
    if group_name in self._data.groups:
      return _Group(self._data.groups[group_name])
    return None

  def ListHosts(self):
    """List hosts."""
    return [_Host(h, self._data.groups[_ROOT_GROUP])
            for h in self._data.hosts.values()]

  def GetHost(self, hostname):
    """Get a host."""
    if hostname in self._data.hosts:
      return _Host(self._data.hosts[hostname], self._data.groups[_ROOT_GROUP])
    return None
