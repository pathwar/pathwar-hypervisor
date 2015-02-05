#!/usr/bin/env python

import requests
import json
import subprocess
import os.path


API_ENDPOINT = 'http://root-token:@212.83.158.125:1337'
REPO_DIR = 'levels'
HOSTNAME= 'techno.sbrk.org'


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

    def get_levels(self):
        """
        I fetch levels from the API.
        """
        url = '{0}/{1}'.format(API_ENDPOINT, 'level-instances?embedded={"level":1}')
        r = requests.get(url)
        if r.status_code == 200:
            levels = []
            content = r.json()
            if '_items' in content:
                for item in content['_items']:
                    levels.append(item['level'])
            return levels
        return None

    def prepare_level(self, level):
        """
        I get and prepare the level.
        """
        level_dir = '{0}/{1}'.format(REPO_DIR, level['name'])
        if os.path.exists(level_dir):
            cmd = 'git pull'.format(level_dir)
            cwd = '{0}/{1}'.format(REPO_DIR, level['name'])
            ret = subprocess.call(cmd, shell=True, cwd=cwd)
        else:
            repo = 'git://github.com/pathwar/level-{0}'.format(level['name'])
            cmd = 'git clone {0} {1}'.format(repo, level_dir)
            ret = subprocess.call(cmd, shell=True)
        return ret == 0

    def inspect_level(self, level):
        """
        I fetch information about the level.
        """
        cwd = '{0}/{1}'.format(REPO_DIR, level['name'])
        cmd = 'fig ps -q'
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

    def run_level(self, level):
        """
        I start the level.
        """
        cmd = 'fig up -d'
        cwd = '{0}/{1}'.format(REPO_DIR, level['name'])
        subprocess.call(cmd, shell=True, cwd=cwd)

    def notify_api(self, level, data):
        """
        I notify the API that a level is up, or not.
        """

        patch_url = '{0}/level-instances/{1}'.format(API_ENDPOINT, level['_id'])

        response = dict()

        # extract HTTP port from port mapping
        response['urls'] = []
        for mapping in data['Ports']:
            if '80/tcp' in mapping:
                host_port = mapping['80/tcp'][0]['HostPort']
                response['urls'].append({'name': 'http', 'url': 'http://{0}:{1}'.format(HOSTNAME, host_port)})

        # extract passphrases
        response['passphrases'] = data['Passphrases']

        r = requests.patch(patch_url, data=response, headers={'If-Match': level['_etag']})
        print(r.status_code)

    def go(self):
        """
        I'm the main.
        """
        levels = self.get_levels()
        if levels:
            for level in levels:
                if self.prepare_level(level):
                    self.run_level(level)
                    data = self.inspect_level(level)
                    self.notify_api(level, data)


if __name__ == '__main__':
    h = Hypervisor()
    h.go()
