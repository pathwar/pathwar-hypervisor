import logging
import random
import subprocess


class Level(object):
    def __init__(id=None, passphrases=None, address=None, dumped_at=None, source=None):
        self.id = id
        self.passphrases = passphrases
        self.address = address
        self.dumped_at = dumped_at
        self.source = source


class DockerDriver(object):
    """ I manage a Docker server. """
    def __init__(self, ip=None):
        self.ip = ip

    def get_running_level_ids(self):
        """ I return the list of IDs of running levels on the host. """

    def destroy_level(self, level_id):
        """ I destroy a level by ID. """

    def create_level(self, tarball):
        """ I create a level from a tarball. """

    def inspect_level(self, level_id):
        """ I inspect a level. """


class DockerPool(object):
    """ I manage a pool of servers. """
    def __init__(self, server_ips):
        # init pool
        self.pool = []
        for server_ip in server_ips:
            self.pool.append(DockerDriver(ip=server))
        # init levels
        self.levels = {}
        for server in self.pool:
            for level_id in server.get_running_level_ids():
                level = server.inspect_level(level_id)
                self.levels[level_id] = (level, server)

    def destroy_level(self, level_id):
        """ I kill a level running on the pool of servers. """
        if level_id in self.levels:
            _, server = self.levels[level_id]
            server.destroy_level(level_id)
            del self.levels[level_id]

    def pick_server(self):
        """ Allocation of levels on servers. """
        return self.pool[int(random.random() * len(self.pool))]

    def get_level(self, level_id):
        if level_id in self.levels:
            level, _ = self.levels[level_id]
            return level

    def create_level(self, tarball):
        """ I randomly create a level on a Docker server. """
        server = self.pick_server()
        level_id = server.create_level(tarball)
        level = server.inspect(level_id)
        self.levels[level_id] = (level, server)
        return level
