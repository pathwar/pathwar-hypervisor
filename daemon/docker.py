import dateutil.parser
import hashlib
import logging
import os
import random
import re
import subprocess
import sys
import socket
import tempfile
import time
import yaml


logger = logging.getLogger('hypervisor')


HTTP_LEVEL_PORT = int(os.environ['HTTP_LEVEL_PORT'])
AUTH_PROXY = os.environ['AUTH_PROXY']


def check_call(*args, **kwargs):
    logger.debug("Executing: {}".format(*args))
    return subprocess.check_call(*args, **kwargs)


def call(*args, **kwargs):
    logger.debug("Executing: {}".format(*args))
    return subprocess.call(*args, **kwargs)


def check_output(*args, **kwargs):
    logger.debug("Executing: {}".format(*args))
    return subprocess.check_output(*args, **kwargs)


class Level(object):
    def __init__(self, id=None, passphrases=None, address=None, dumped_at=None, version=None, source=None):
        self.id = id
        self.passphrases = passphrases
        self.address = address
        self.dumped_at = dumped_at
        self.version = version
        self.source = source


class DockerDriver(object):
    """ I manage a Docker server. """
    def __init__(self, host=None):
        self.host = host
        if '@' in host:
            self.ip = host.split('@')[1]
        else:
            self.ip = host
        ssh_options = '-o ControlMaster=auto -o ControlPersist=10m -o ControlPath=~/%r@%h:%p -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no'
        self.ssh = 'ssh {0} {1}'.format(host, ssh_options)
        self.scp = 'scp {0}'.format(ssh_options)

        self._setup_nginx_proxy()

    def _setup_nginx_proxy(self):
        """ I ensure the nginx proxy is up. """

        docker_compose = """# generated by the hypervisor
proxy:
  image: jwilder/nginx-proxy:latest
  ports:
  - {0}:80
  volumes:
  - /var/run/docker.sock:/tmp/docker.sock
  - ./my_proxy.conf:/etc/nginx/conf.d/my_proxy.conf
  restart: always
""".format(HTTP_LEVEL_PORT)

        my_proxy = """
allow {0};
deny all;

proxy_set_header Authorization "";
""".format(socket.gethostbyname(AUTH_PROXY))

        try:
            # create dir if not exists
            cmd = '{0} "mkdir -p hypervisor-nginx-proxy"'.format(self.ssh)
            call(cmd, shell=True)

            # overwrite compose file
            fd, tmpfile = tempfile.mkstemp()
            os.write(fd, docker_compose)
            os.close(fd)
            cmd = '{0} {1} {2}:hypervisor-nginx-proxy/docker-compose.yml'.format(self.scp, tmpfile, self.host)
            check_call(cmd, shell=True)
            os.remove(tmpfile)

            # overwrite the config
            fd, tmpfile = tempfile.mkstemp()
            os.write(fd, my_proxy)
            os.close(fd)
            cmd = '{0} {1} {2}:hypervisor-nginx-proxy/my_proxy.conf'.format(self.scp, tmpfile, self.host)
            check_call(cmd, shell=True)
            os.remove(tmpfile)

            # docker-compose up the proxy
            logger.info('running nginx-proxy on {0}'.format(self.host))
            cmd = '{0} "cd hypervisor-nginx-proxy ; docker-compose up -d"'.format(self.ssh)
            call(cmd, shell=True)
        except Exception as e:
            logger.warning('failed to setup nginx proxy server on {0}'.format(self.host),  exc_info=True)

    def _get_compose(self, level_id):
        """ I return the docker-compose.yml file of a level. """
        cmd = '{0} cat levels/{1}/docker-compose.yml'.format(self.ssh, level_id)
        return yaml.load(check_output(cmd, shell=True))

    def _write_compose(self, level_id, compose):
        """ I write back the docker-compose.yml file of a level. """
        fd, tmpfile = tempfile.mkstemp()
        os.write(fd, yaml.dump(compose, default_flow_style=False))
        os.close(fd)
        cmd = '{0} {1} {2}:levels/{3}/docker-compose.yml'.format(self.scp, tmpfile, self.host, level_id)
        check_call(cmd, shell=True)
        os.remove(tmpfile)

    def get_running_level_ids(self):
        """ I return the list of IDs of running levels on the host. """
        uuids = set()
        cmd = '{0} "docker ps --no-trunc"'.format(self.ssh)
        for line in check_output(cmd, shell=True).splitlines():
            m = re.match('^.*([a-z0-9]{32})_.*_.*$', line)
            if m:
                uuid_merged = m.group(1)
                uuid = '{0}-{1}-{2}-{3}-{4}'.format(uuid_merged[:8],
                                                    uuid_merged[8:12],
                                                    uuid_merged[12:16],
                                                    uuid_merged[16:20],
                                                    uuid_merged[20:32])
                uuids.add(uuid)
        return uuids

    def destroy_level(self, level_id):
        """ I destroy a level by ID. """

        level_type = self.get_level_type(level_id)
        if level_type == "unix":
            cmd = "{0} 'docker ps -q --filter=label=ssh2docker --filter=image=unix-{1} | xargs docker kill'".format(self.ssh, level_id)
            call(cmd, shell=True)

        # stopping level
        logger.info('stopping level {0} on {1}'.format(level_id, self.host))
        cwd = 'levels/{0}'.format(level_id)
        cmd = '{0} "test -d {1} && (cd {1} ; docker-compose kill; docker-compose rm -fv)"'.format(self.ssh, cwd)
        call(cmd, shell=True)

    def rebuild_if_needed(self, level_id, tarball, conf):
            # never reached if level is not needed
            m = re.match('image\-for\-(.*)', conf['image'])
            if m:
                try:
                    cmd = '{0} "cat levels/{1}/REBUILD"'.format(self.ssh, level_id)
                    check_call(cmd, shell=True)
                    # raise here if level has no REBUILD file
                except:
                    logger.info('do not rebuild level image for {0}, not changed'.format(level_id))
                    return



                # FIXME: removing level
                # logger.info('removing level {0} on {1}'.format(level_id, self.host))
                # cwd = 'levels/{0}'.format(level_id)
                # cmd = '{0} "cd {1} ; docker-compose rm -f"'.format(self.ssh, cwd)
                # call(cmd, shell=True)


                # rebuild
                logger.info('rebuilding level image for {0}'.format(level_id))
                tarball = '{0}.tar'.format(m.group(1))
                logger.info('importing {0}'.format(conf['image']))
                cwd = 'levels/{0}'.format(level_id)
                cmd = '{0} "cd {1} ; cat {2} | docker import - {3}"'.format(self.ssh, cwd, tarball, conf['image'])
                check_call(cmd, shell=True)

                # patching docker-compose so it contains a VIRTUAL_HOST entry
                # (required by nginx-proxy), we generate a random one only known
                # to the authproxy module.
                conf['environment'] = conf.get('environment', [])
                print(conf.get('environment'))
                if isinstance(conf['environment'], list):
                    conf['environment'] = {
                        line.split("=")[0]: line.split("=")[1]
                        for line in conf['environment']
                    }
                conf['environment']['VIRTUAL_HOST'] = conf['environment'].get('VIRTUAL_HOST', str(level_id))
                print(conf.get('environment'))

            # cleanup for next rebuild
            cmd = '{0} "rm -f levels/{1}/REBUILD"'.format(self.ssh, level_id)
            call(cmd, shell=True)

    def create_level(self, level_id, tarball):
        """ I create a level from a tarball. """

        # download the tarball remotely
        logger.info('downloading {0}'.format(tarball))
        hashtar = hashlib.sha224(tarball).hexdigest()
        cmd = '{0} "wget -nc -q {1} -O /tmp/{2}"'.format(self.ssh, tarball, hashtar)
        call(cmd, shell=True)

        # only extract level if source changed
        logger.info('extracting level on {0}'.format(self.host))
        source = 'levels/{0}/source'.format(level_id)
        cmd = '{0} \'test -f {1} && [ $(cat {1}) = {2} ] || (mkdir -p levels/{4} ; tar -xf /tmp/{3} -C levels/{4} ; echo {2} > {1} ; touch levels/{4}/REBUILD)\''.format(self.ssh, source, tarball, hashtar, level_id)
        check_call(cmd, shell=True)

        # preparing level image
        logger.info('preparing level image')
        compose = self._get_compose(level_id)
        modified = {}
        for service, conf in compose.iteritems():
            if 'image' in conf:
                self.rebuild_if_needed(level_id, tarball, conf)
            modified[service] = conf
        self._write_compose(level_id, modified)

        # building level
        logger.info('building level {0} on {1}'.format(level_id, self.host))
        cwd = 'levels/{0}'.format(level_id)
        cmd = '{0} "cd {1} ; docker-compose build"'.format(self.ssh, cwd)
        check_call(cmd, shell=True)

        main = compose.keys()[0]
        section = compose.values()[0]
        level_type = section.get('labels', {}).get('PATHWAR_LEVEL_TYPE', 'web')
        level_type = section.get('labels', {}).get('PWR_LEVEL_TYPE', 'web')
        if level_type == "unix":
            # FIXME: docker ps -lq is not thread safe
            # we should use the docker-compose feature: name
            cmd = '{0} "cd {1}; docker-compose run {2}; docker commit \`docker ps -lq\` unix-{3}"'.format(self.ssh, cwd, main, str(level_id))
            check_call(cmd, shell=True)
            print("DOCKER_COMPOSE", level_type)
        else:
            # running level
            logger.info('running level {0} on {1}'.format(level_id, self.host))
            cwd = 'levels/{0}'.format(level_id)
            cmd = '{0} "cd {1} ; docker-compose up -d"'.format(self.ssh, cwd)
            check_call(cmd, shell=True)

        return True

    def get_level_type(self, level_id):
        compose = self._get_compose(level_id)
        section = compose.values()[0]
        level_type = section.get('labels', {}).get('PATHWAR_LEVEL_TYPE', 'web')
        level_type = section.get('labels', {}).get('PWR_LEVEL_TYPE', 'web')
        return level_type

    def inspect_level(self, level_id):
        """ I inspect a level. """
        level = Level()
        level.id = level_id

        # fetch passphrases, uptime and version
        level.dumped_at = None
        level.version = None
        level.tarball = None
        level.passphrases = []
        logger.info('fetching passphrases for {0} on {1}'.format(level_id, self.host))
        level_type = self.get_level_type(level_id)
        if level_type == "unix":
            cmd = '{0} "docker run --entrypoint=bash --rm unix-{1} -c \'for file in /pathwar/passphrases/*; do echo -n \\"\\$(basename \\$file) \\"; cat \\$file; done\'"'.format(self.ssh, level_id)
            for line in check_output(cmd, shell=True).splitlines():
                chunks = line.split()
                if len(chunks) == 2:
                    logger.info('found passphrase {0} for {1} on {2}'.format(chunks[0], level_id, self.host))
                    level.passphrases.append({'key': chunks[0], 'value': chunks[1]})
                    # FIXME: set level.dumpet_at to the image build date
                    # FIXME: set level.version
        else:
            cwd = 'levels/{0}'.format(level_id)
            cmd = '{0} "cd {1} ; docker-compose ps -q"'.format(self.ssh, cwd)
            for docker_uuid in check_output(cmd, shell=True).splitlines():
                if not level.dumped_at:
                    cmd = '{0} "docker inspect -f {{{{.State.StartedAt}}}} {1}"'.format(self.ssh, docker_uuid)
                    uptime = check_output(cmd, shell=True).strip()
                    level.dumped_at = dateutil.parser.parse(uptime)
                    logger.info('found dumped_at {0} for {1} on {2}'.format(level.dumped_at, level_id, self.host))

                if not level.version:
                    try:
                        # here, it is fine to fail
                        cmd = '{0} "docker exec {1} bash -c \'grep version /pathwar/level.yml | awk \\"// {{ print \\$2; }}\\"\'"'.format(self.ssh, docker_uuid)
                        version = check_output(cmd, shell=True).strip()
                        if len(version):
                            logger.info('found version {0} for {1} on {2}'.format(version, level_id, self.host))
                            level.version = version
                    except:
                        pass

                try:
                    # here, it is fine to fail, not all containers have passphrases.
                    # please, be careful with this line, this is really tricky (there
                    # are several levels of inhibition mixing together).
                    cmd = '{0} "docker exec {1} bash -c \'for file in /pathwar/passphrases/*; do echo -n \\"\\$(basename \\$file) \\"; cat \\$file; done\'"'.format(self.ssh, docker_uuid)
                    for line in check_output(cmd, shell=True).splitlines():
                        chunks = line.split()
                        if len(chunks) == 2:
                            logger.info('found passphrase {0} for {1} on {2}'.format(chunks[0], level_id, self.host))
                            level.passphrases.append({'key': chunks[0], 'value': chunks[1]})
                except:
                    pass

        try:
            cmd = '{0} "cat levels/{1}/source"'.format(self.ssh, level_id)
            level.source = check_output(cmd, shell=True).strip()
        except Exception as e:
            logger.warning("failed to find source on server {0} for level {1}".format(self.host, level_id), exc_info=True)
            pass

        level.address = self.ip

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

    def load(self):
        for server in self.pool:
            for level_id in server.get_running_level_ids():
                level = server.inspect_level(level_id)
                self.levels[level_id] = (level, server)

    def _pick_server(self):
        """ Allocation of levels on servers. """
        return self.pool[int(random.random() * len(self.pool))]

    def destroy_blindly(self, level_instance_id):
        """ I blindly kill a level running on the pool of servers. """
        for server in self.pool:
            server.destroy_level(level_instance_id)
            if level_instance_id in self.levels:
                del self.levels[level_instance_id]

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
                level = server.inspect_level(level_id)
                self.levels[level_id] = (level, server)
                return level

    def get_level_type(self, level_id):
        """ I get the level type. """
        server = self._pick_server()
        if server:
            return server.get_level_type(level_id)
