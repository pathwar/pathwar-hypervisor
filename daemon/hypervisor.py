#!/usr/bin/env python

import requests
import json
import logging
import tempfile
import subprocess
import os.path
import shutil
import time


# configured via docker-compose.yml
API_ENDPOINT = os.environ['API_ENDPOINT']
HOSTNAME= os.environ['HOSTNAME']

# misc
REPO_DIR = 'levels'

class Hypervisor:

    """
    Hi, I'm the hypervisor:
    - I fetch levels
    - I dump levels
    - I notify the API
    - I sleep
    """

    def __init__(self):
        """
        I setup the Hypervisor.
        """
        if not os.path.exists(REPO_DIR):
            os.mkdir(REPO_DIR)

    def get_level_instances(self):
        """
        I fetch levels from the API.
        """
        url = '{0}/{1}'.format(API_ENDPOINT, 'level-instances?embedded={"level":1}')
        r = requests.get(url)
        if r.status_code == 200:
            level_instances = []
            content = r.json()
            if '_items' in content:
                for item in content['_items']:
                    level_instances.append(item)
            return level_instances
        return None

    def level_exists(self, level_dir):
        return os.path.exists(level_dir)

    def level_needs_redump(self, level_dir, level_url):
        try:
            with open('{0}/VERSION'.format(level_dir)) as fh:
                current_url = fh.read()
                if current_url != level_url:
                    return True
            with open('{0}/REDUMP'.format(level_dir)) as fh:
                next_redump = int(fh.read())
                return int(time.time()) >= next_redump
        except:
            pass
        return True

    def get_next_level_redump_at(self, level_dir):
        with open('{0}/REDUMP'.format(level_dir)) as fh:
            return int(fh.read())

    def prepare_level(self, level_instance):
        """
        I get and prepare the level, I return true if the level is to be ran.
        """
        level = level_instance['level']
        level_dir = '{0}/{1}'.format(REPO_DIR, level['name'])
        level_url = level['url']

        logging.info('checking level {0}'.format(level['name']))
        if not level_instance['active'] or not level['url']:
            return False
        if level_exists(level_dir) and not level_needs_redump(level_dir, level_url):
            return False

        logging.info('preparing level {0}'.format(level['name']))

        tmp = tempfile.mkdtemp()
        try:
            logging.info('setting version for level {0}'.format(level['name']))
            with open('{0}/VERSION'.format(tmp), 'w+') as fh:
                fh.write(level_url)

            logging.info('setting next redump timestamp {0}'.format(level['name']))
            with open('{0}/REDUMP'.format(tmp), 'w+') as fh:
                next_redump_at = int(time.time() + level['redump'])
                fh.write('{0}'.format(next_redump_at))

            logging.info('downloading package for level {0}'.format(level['name']))
            cmd = 's3cmd get {0} {1}/package.tar'.format(level['url'], tmp)
            subprocess.call(cmd, shell=True)

            logging.info('extracting level {0}'.format(level['name']))
            cmd = 'tar -xf {0}/package.tar -C {0}'.format(tmp)
            subprocess.call(cmd, shell=True)

            logging.info('moving level {0}'.format(level['name']))
            cmd = 'mv {0} {1}'.format(tmp, level_dir)
            subprocess.call(cmd, shell=True)

            logging.info('building level {0}'.format(level['name']))
            cmd = 'docker-compose -f {0}/docker-compose.yml build'.format(level_dir)
            subprocess.call(cmd, shell=True)
            return True
        except:
            logging.wanring('failed to prepare level {0}'.format(level['name']))
            shutil.rmtree(tmp)
            return False

    def inspect_level(self, level_instance):
        """
        I fetch information about the level.
        """
        level = level_instance['level']
        cwd = '{0}/{1}'.format(REPO_DIR, level['name'])
        cmd = 'docker-compose ps -q'
        passphrases = []
        ports = []
        for container in subprocess.check_output(cmd, shell=True, cwd=cwd).splitlines():
            # passphrases
            cmd = "docker exec {0} /bin/sh -c 'for file in /pathwar/passphrases/*; do echo -n \"$(basename $file) \"  ; cat $file; done'".format(container)
            for line in subprocess.check_output(cmd, shell=True).splitlines():
                chunks = line.split()
                if len(chunks) == 2:
                    passphrases.append({'key': chunks[0], 'value': chunks[1]})
            # ports mappings
            cmd = 'docker inspect {0}'.format(container)
            res = json.loads(subprocess.check_output(cmd, shell=True))
            if len(res):
                data = res[0]
                if 'Ports' in data['NetworkSettings']:
                    ports.append(data['NetworkSettings']['Ports'])
        return {'Ports': ports, 'Passphrases': passphrases}

    def run_level(self, level_instance):
        """
        I start the level.
        """
        level = level_instance['level']
        cmd = 'docker-compose up -d'
        cwd = '{0}/{1}'.format(REPO_DIR, level['name'])
        subprocess.call(cmd, shell=True, cwd=cwd)

    def notify_api(self, level_instance, data):
        """
        I notify the API that a level is up, or not.
        """

        level = level_instance['level']
        patch_url = '{0}/level-instances/{1}'.format(API_ENDPOINT, level_instance['_id'])

        response = dict()

        # extract HTTP port from port mapping
        response['urls'] = []
        for mapping in data['Ports']:
            if '80/tcp' in mapping:
                host_port = mapping['80/tcp'][0]['HostPort']
                response['urls'].append({'name': 'http', 'url': 'http://{0}:{1}'.format(HOSTNAME, host_port)})

        # extract passphrases
        response['passphrases'] = data['Passphrases']
        print('response: {}'.format(response))

        headers = {
            'If-Match': level_instance['_etag'],
            'Content-Type': 'application/json',
        }

        r = requests.patch(patch_url, data=json.dumps(response), headers=headers)
        print(r.status_code, r.json())

    def go(self):
        """
        I'm the main.
        """
        while True:
            logging.info('waiting for more work')
            level_instances = self.get_level_instances()
            if level_instances:
                for level_instance in level_instances:
                    if self.prepare_level(level_instance):
                        pass
            time.sleep(5)
#                    self.run_level(level_instance)
#                    data = self.inspect_level(level_instance)
#                    self.notify_api(level_instance, data)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    h = Hypervisor()
    h.go()
