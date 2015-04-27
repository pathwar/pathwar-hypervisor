import logging
import random
import re
import subprocess
import sys
import yaml


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
        self.scp = 'scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no'

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
        # locally download the tarball
        logging.info('downloading {0}'.format(tarball))
        cmd = 'wget -q {0} -O /tmp/hypervisor-temp-level.tar'.format(tarball)
        subprocess.check_call(cmd, shell=True)

        # uploading it to the server
        logging.info('uploading to {0}'.format(self.host))
        cmd = '{0} /tmp/hypervisor-temp-level.tar {1}:/tmp/hypervisor-level-to-build.tar'.format(self.scp, self.host)
        subprocess.check_call(cmd, shell=True)

        # extract level
        logging.info('extracting level on {0}'.format(self.host))
        cmd = '{0} "mkdir -p levels/{1} ; tar -xf /tmp/hypervisor-level-to-build.tar -C levels/{1} ; rm -f /tmp/hypervisor-level-to-build.tar"'.format(self.ssh, level_id)
        subprocess.check_call(cmd, shell=True)

        # preparing level image
        logging.info('preparing level image')
        cmd = '{0} cat levels/{1}/docker-compose.yml'.format(self.ssh, level_id)
        compose = yaml.load(subprocess.check_output(cmd, shell=True))
        for service, conf in compose.iteritems():
            if 'image' in conf:
                m = re.match('image\-for\-(.*)', conf['image'])
                if m:
                    tarball = '{0}.tar'.format(m.group(1))
                    logging.info('importing {0}'.format(conf['image']))
                    cwd = 'levels/{0}'.format(level_id)
                    cmd = '{0} "cd {1} ; cat {2} | docker import - {3}"'.format(self.ssh, cwd, tarball, conf['image'])
                    subprocess.check_call(cmd, shell=True)

        # building level
        logging.info('building level {0} on {1}'.format(level_id, self.host))
        cwd = 'levels/{0}'.format(level_id)
        cmd = '{0} "cd {1} ; docker-compose build"'.format(self.ssh, cwd)
        subprocess.check_call(cmd, shell=True)

        # running level
        logging.info('running level {0} on {1}'.format(level_id, self.host))
        cwd = 'levels/{0}'.format(level_id)
        cmd = '{0} "cd {1} ; docker-compose up -d"'.format(self.ssh, cwd)
        subprocess.check_call(cmd, shell=True)

        # FIXME: refresh nginx

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
