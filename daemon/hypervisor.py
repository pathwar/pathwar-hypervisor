#!/usr/bin/env python

import requests
import json
import logging
import tempfile
import subprocess
import os.path
import re
import shutil
import sys
import time
import yaml

from docker import DockerPool


# configured via docker-compose.yml
API_ENDPOINT = os.environ['API_ENDPOINT']
DOCKER_POOL = os.environ['DOCKER_POOL'].split(',')
REFRESH_RATE = int(os.environ['REFRESH_RATE'])

class Hypervisor(object):
    def __init__(self):
        self.pool = DockerPool(DOCKER_POOL)

    def loop(self):
        while True:
            logging.debug('wakup Neo')

            for api_level_instance in self.api_fetch_level_instances():
                level_id = api_level_instance['_id']
                api_level = api_level_instance['level']

                # ignore level if incomplete
                if 'url' not in api_level or not api_level_instance['active']:
                    logging.debug('ignored level {0}'.format(level_id))
                    continue

                level = self.pool.get_level(level_id)

                # create level if not exist
                if not level:
                    logging.info('creating level {0}'.format(level_id))
                    level = self.pool.create_level(level_id, api_level['url'])
                    self.api_update_level_instance(api_level, level)
                    continue

                # refresh/redump level if needed
                level_changed = level.source != api_level['url']
                level_redump = api_level['defaults']['redump']
                level_next_redump = level.dumped_at + level_redump
                level_need_redump = level_next_redump < int(time.time())
                if level_changed or level_need_redump:
                    logging.info('redumping level {0}'.format(level_id))
                    self.destroy_level(level_id)
                    self.pool.create_level(level_idapi_level['url'])
                    level = self.pool.get_level(level_id)
                    self.api_update_level_instance(api_level, level)
                    continue

            time.sleep(REFRESH_RATE)

    def api_update_level_instance(self, api_level_instance, level):
        """ I update the state of a level on the API. """
        level_id = api_level_instance['_id']
        logging.info('patching API for {0}'.format(level_id))
        patch_url = '{0}/level-instances/{1}'.format(API_ENDPOINT, level_id)
        response = dict()

        # extract HTTP port from port mapping
        response['urls'] = []
        for mapping in data['Ports']:
            if '80/tcp' in mapping:
                host_port = mapping['80/tcp'][0]['HostPort']
                response['urls'].append({'name': 'http', 'url': 'http://{0}/'.format(level.address)})

        # extract passphrases
        response['passphrases'] = data['Passphrases']

        headers = {
            'If-Match': level_instance['_etag'],
            'Content-Type': 'application/json',
        }

        r = requests.patch(patch_url, data=json.dumps(response), headers=headers)

    def api_fetch_level_instances(self):
        """ I fetch level instances from the API. """
        url = '{0}/{1}'.format(API_ENDPOINT, 'level-instances?embedded={"level":1}')
        r = requests.get(url)
        if r.status_code == 200:
            level_instances = []
            content = r.json()
            if '_items' in content:
                for item in content['_items']:
                    level_instances.append(item)
            return level_instances


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    h = Hypervisor()
    h.loop()

#class Hypervisor(object):
#
#    """
#    Hi, I'm the hypervisor:
#    - I fetch levels
#    - I dump levels
#    - I notify the API
#    - I sleep
#    """
#
#    def __init__(self):
#        """
#        I setup the Hypervisor.
#        """
#        if not os.path.exists(REPO_DIR):
#            os.mkdir(REPO_DIR)
#
#    def get_level_instances(self):
#        """
#        I fetch levels from the API.
#        """
#        url = '{0}/{1}'.format(API_ENDPOINT, 'level-instances?embedded={"level":1}')
#        r = requests.get(url)
#        if r.status_code == 200:
#            level_instances = []
#            content = r.json()
#            if '_items' in content:
#                for item in content['_items']:
#                    level_instances.append(item)
#            return level_instances
#        return None
#
#    def level_exists(self, level_dir):
#        return os.path.exists(level_dir)
#
#    def level_needs_redump(self, level_dir, level_url):
#        try:
#            with open('{0}/VERSION'.format(level_dir)) as fh:
#                current_url = fh.read()
#                if current_url != level_url:
#                    return True
#            with open('{0}/REDUMP'.format(level_dir)) as fh:
#                next_redump = int(fh.read())
#                return int(time.time()) >= next_redump
#            # FIXME ensure level is UP
#        except:
#            pass
#        return True
#
#    def get_next_level_redump_at(self, level_dir):
#        with open('{0}/REDUMP'.format(level_dir)) as fh:
#            return int(fh.read())
#
#    def prepare_level(self, level_instance):
#        """
#        I get and prepare the level, I return true if the level is to be ran.
#        """
#        level = level_instance['level']
#        level_dir = '{0}/{1}'.format(REPO_DIR, level['name'])
#
#        if not level_instance['active'] or not 'url' in level:
#            return False
#        if self.level_exists(level_dir) and not\
#           self.level_needs_redump(level_dir, level['url']):
#            return False
#
#        logging.info('preparing level {0}'.format(level['name']))
#
#        tmp = tempfile.mkdtemp()
#        try:
#            logging.info('setting version for level {0}'.format(
#                level['name']))
#            with open('{0}/VERSION'.format(tmp), 'w+') as fh:
#                fh.write(level['url'])
#
#            logging.info('setting next redump timestamp {0}'.format(
#                level['name']))
#
#            with open('{0}/REDUMP'.format(tmp), 'w+') as fh:
#                next_redump_at = int(time.time() + level['defaults']['redump'])
#                fh.write('{0}'.format(next_redump_at))
#
#            logging.info('downloading package for level {0}'.format(
#                level['name']))
#            cmd = 's3cmd get {0} {1}/package.tar'.format(level['url'], tmp)
#            subprocess.check_call(cmd, shell=True)
#
#            logging.info('extracting level {0}'.format(level['name']))
#            cmd = 'tar -xf {0}/package.tar -C {0}'.format(tmp)
#            subprocess.check_call(cmd, shell=True)
#
#            logging.info('moving level {0}'.format(level['name']))
#            cmd = 'mv {0} {1}'.format(tmp, level_dir)
#            subprocess.check_call(cmd, shell=True)
#
#            logging.info('creating images for level {0}'.format(level['name']))
#            with open('{0}/docker-compose.yml'.format(level_dir)) as fh:
#                origin = yaml.safe_load(fh)
#                output = dict()
#                for name, conf in origin.iteritems():
#                    if 'image' in conf:
#                        m = re.match('image\-for\-(.*)', conf['image'])
#                        if m:
#                            tarball = '{0}/{1}.tar'.format(level_dir, m.group(1))
#                            logging.info('converting export {0} to image {1}'\
#                                         .format(tarball, conf['image']))
#                            cmd = 'cat {0} | docker import - {1}'.format(tarball, conf['image'])
#                            subprocess.check_call(cmd, shell=True)
#            logging.info('level {0} prepared'.format(level['name']))
#            return True
#        except Exception as error:
#            logging.warning('failed to prepare level {0}: {1}'.format(
#                level['name'], error))
#            sys.exit(1)
#            shutil.rmtree(tmp)
#            return False
#
#    def inspect_level(self, level_instance):
#        """
#        I fetch information about the level.
#        """
#        level = level_instance['level']
#        cwd = '{0}/{1}'.format(REPO_DIR, level['name'])
#        cmd = 'docker-compose ps -q'
#        passphrases = []
#        ports = []
#        time.sleep(1)
#        for container in subprocess.check_output(cmd, shell=True, cwd=cwd).splitlines():
#            logging.info('generating passphrase for level {0}'.format(level['name']))
#            # passphrases
#            cmd = "docker exec {0} /bin/sh -c \'for file in /pathwar/passphrases/*; do echo -n \"$(basename $file)\"; cat $file; done\'".format(container)
#            for line in subprocess.check_output(cmd, shell=True).splitlines():
#                chunks = line.split()
#                if len(chunks) == 2:
#                    passphrases.append({'key': chunks[0], 'value': chunks[1]})
#            # ports mappings
#            cmd = 'docker inspect {0}'.format(container)
#            res = json.loads(subprocess.check_output(cmd, shell=True))
#            if len(res):
#                data = res[0]
#                if 'Ports' in data['NetworkSettings']:
#                    ports.append(data['NetworkSettings']['Ports'])
#        return {'Ports': ports, 'Passphrases': passphrases}
#
#    def run_level(self, level_instance):
#        """
#        I start the level.
#        """
#        level = level_instance['level']
#        logging.info('running level {0}'.format(level['name']))
#
#        cwd = '{0}/{1}'.format(REPO_DIR, level['name'])
#        cmd = 'docker-compose stop'
#        subprocess.check_call(cmd, shell=True, cwd=cwd)
#        cmd = 'docker-compose rm -f'
#        subprocess.check_call(cmd, shell=True, cwd=cwd)
#        cmd = 'docker-compose up -d'
#        subprocess.check_call(cmd, shell=True, cwd=cwd)
#
#    def destroy_level(self, level_instance):
#        """
#        I destroy the level.
#        """
#        level = level_instance['level']
#        cwd = '{0}/{1}'.format(REPO_DIR, level['name'])
#
#        cmd = 'docker-compose stop'
#        subprocess.call(cmd, shell=True, cwd=cwd)
#
#        cmd = 'docker-compose rm -f'
#        subprocess.call(cmd, shell=True, cwd=cwd)
#
#        shutil.rmtree(cwd)
#
#    def notify_api(self, level_instance, data):
#        """
#        I notify the API that a level is up, or not.
#        """
#
#        level = level_instance['level']
#        logging.info('notifying API that level {0} is ready'.format(level['name']))
#        patch_url = '{0}/level-instances/{1}'.format(API_ENDPOINT, level_instance['_id'])
#
#        response = dict()
#
#        # extract HTTP port from port mapping
#        response['urls'] = []
#        for mapping in data['Ports']:
#            if '80/tcp' in mapping:
#                host_port = mapping['80/tcp'][0]['HostPort']
#                response['urls'].append({'name': 'http', 'url': 'http://{0}:{1}'.format(HOSTNAME, host_port)})
#
#        # extract passphrases
#        response['passphrases'] = data['Passphrases']
#        print('response: {}'.format(response))
#
#        headers = {
#            'If-Match': level_instance['_etag'],
#            'Content-Type': 'application/json',
#        }
#
#        r = requests.patch(patch_url, data=json.dumps(response), headers=headers)
#        print(r.status_code, r.json())
#
#    def go(self):
#        """
#        I'm the main.
#        """
#        while True:
#            logging.info('waiting for more work')
#            level_instances = self.get_level_instances()
#            if level_instances:
#                for level_instance in level_instances:
#                    if self.prepare_level(level_instance):
#                        self.run_level(level_instance)
#                        data = self.inspect_level(level_instance)
#                        self.notify_api(level_instance, data)
#            time.sleep(5)
#
#
#if __name__ == '__main__':
#   logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
#   h = Hypervisor()
#   h.go()
