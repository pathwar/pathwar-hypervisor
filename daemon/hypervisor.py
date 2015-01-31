#!/usr/bin/env python

import requests
import json
import subprocess
import os.path


API_ENDPOINT = 'http://root-token:@212.83.158.125:1337/level-instances?embedded={"level":1}'
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

    def get_levels(self):
        """
        I fetch levels from the API.
        """
        r = requests.get(API_ENDPOINT)
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
        for container in subprocess.check_output(cmd, shell=True, cwd=cwd).splitlines():
            print container

    def run_level(self, level):
        """
        I start the level.
        """
        cmd = 'fig up -d'
        cwd = '{0}/{1}'.format(REPO_DIR, level['name'])
        subprocess.call(cmd, shell=True, cwd=cwd)

    def go(self):
        """
        I'm the main.
        """
        levels = self.get_levels()
        if levels:
            for level in levels:
                if self.prepare_level(level):
                    self.run_level(level)
                    self.inspect_level(level)


if __name__ == '__main__':
    h = Hypervisor()
    h.go()
