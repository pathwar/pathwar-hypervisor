import logging
import random
import re
import subprocess
import sys


class Level(object):
    def __init__(id=None, passphrases=None, address=None, dumped_at=None, source=None):
        self.id = id
        self.passphrases = passphrases
        self.address = address
        self.dumped_at = dumped_at
        self.source = source


class DockerDriver(object):
    """ I manage a Docker server. """
    def __init__(self, host=None):
        self.host = host
        self.ssh = 'ssh {0} -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no'.format(host)

    def get_running_level_ids(self):
        """ I return the list of IDs of running levels on the host. """
        uuids = []
        cmd = '{0} "docker ps --no-trunc"'.format(self.ssh)
        for line in subprocess.check_output(cmd, shell=True).split('\n'):
            m = re.match('^.*(a-zA-Z0-9]{32})_([^_]+)_([^_]+)$', line)
            if m:
                uuid_merged = m.group(1)
                uuid = '{0}-{1}-{2}-{3}-{4}'.format(uuid_merged[:8],
                                                    uuid_merged[8:12],
                                                    uuid_merged[12:16],
                                                    uuid_merged[16:20],
                                                    uuid_merged[20:32])
                uuids.append(uuid)
        return uuids

    def destroy_level(self, level_id):
        """ I destroy a level by ID. """
        # FIXME
        # - on the server:
        #   - docker-compose stop
        #   - docker-compose rm
        #   - rmdir /levels/{id}
        # - refresh nginx

    def create_level(self, level_id, tarball):
        """ I create a level from a tarball. """
        # FIXME
        # - locally download tarball
        # - upload it to the server
        # - on the server:
        #   - mkdir /levels/{id}
        #   - extract
        #   - export
        #   - docker-compose up
        # - remove tarball
        # - refresh nginx

    def inspect_level(self, level_id):
        """ I inspect a level. """
        level = Level()
        level.id = level_id
        # FIXME
        # - fetch passphrases
        # - fetch addresses
        # - fetch dumped_at
        # - fetch source
        return level


class DockerPool(object):
    """ I manage a pool of Docker servers. """
    def __init__(self, server_ips):
        # init pool
        self.pool = []
        for server_ip in server_ips:
            self.pool.append(DockerDriver(host=server_ip))
        # init levels
        self.levels = {}
        for server in self.pool:
            for level_id in server.get_running_level_ids():
                level = server.inspect_level(level_id)
                self.levels[level_id] = (level, server)

    def _pick_server(self):
        """ Allocation of levels on servers. """
        return self.pool[int(random.random() * len(self.pool))]

    def destroy_level(self, level_id):
        """ I kill a level running on the pool of servers. """
        if level_id in self.levels:
            _, server = self.levels[level_id]
            server.destroy_level(level_id)
            del self.levels[level_id]

    def get_level(self, level_id):
        if level_id in self.levels:
            level, _ = self.levels[level_id]
            return level

    def create_level(self, level_id, tarball):
        """ I randomly create a level on a Docker server. """
        server = self._pick_server()
        if server:
            if server.create_level(level_id, tarball):
                level = server.inspect(level_id)
                self.levels[level_id] = (level, server)
                return level
