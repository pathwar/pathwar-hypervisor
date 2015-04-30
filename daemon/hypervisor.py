#!/usr/bin/env python

import requests
import json
import logging.config
import logging
import tempfile
import traceback
import subprocess
import os.path
import raven
import re
import shutil
import sys
import time
import yaml

from docker import DockerPool
from raven.handlers.logging import SentryHandler
from raven.conf import setup_logging


logger = logging.getLogger('hypervisor')


# configured via docker-compose.yml
API_ENDPOINT = os.environ['API_ENDPOINT']
DOCKER_POOL = os.environ['DOCKER_POOL'].split(',')
REFRESH_RATE = int(os.environ['REFRESH_RATE'])
HTTP_LEVEL_PORT = int(os.environ['HTTP_LEVEL_PORT'])
SENTRY_URL = os.environ['SENTRY_URL']

class Hypervisor(object):
    def __init__(self):
        logger.info('starting the hypervisor')
        self.pool = DockerPool(DOCKER_POOL)

    def manage_level(self, api_level_instance):
        """ I manage a level instance, create it, redump if needed, ... """
        level_id = api_level_instance['_id']
        api_level = api_level_instance['level']

        # ignore level if incomplete
        if 'url' not in api_level or not api_level_instance['active']:
            logger.debug('ignored level {0}'.format(level_id))
            return

        level = self.pool.get_level(level_id)

        # create level if not exist
        if not level:
            logger.info('creating level {0}'.format(level_id))
            level = self.pool.create_level(level_id, api_level['url'])
            self.api_update_level_instance(api_level_instance, level)
            return

        # refresh/redump level if needed
        level_changed = False # FIXME: level.version != api_level['version']
        level_redump = api_level['defaults']['redump']
        level_next_redump = level.dumped_at + level_redump
        level_need_redump = level_next_redump < int(time.time())
        if level_changed or level_need_redump:
            logger.info('redumping level {0}'.format(level_id))
            self.pool.destroy_level(level_id)
            self.pool.create_level(level_id, api_level['url'])
            level = self.pool.get_level(level_id)
            self.api_update_level_instance(api_level_instance, level)
            return

    def loop(self):
        """ I'm the main loop of the hypervisor. """
        while True:
            logger.info('wake-up Neo')
            for api_level_instance in self.api_fetch_level_instances():
                try:
                    self.manage_level(api_level_instance)
                except Exception as e:
                    logger.warning('had a problem while managing level {0}: {1}'.format(api_level_instance['_id'], str(e)), exc_info=True)
            time.sleep(REFRESH_RATE)

    def api_update_level_instance(self, api_level_instance, level):
        """ I update the state of a level on the API. """
        level_id = api_level_instance['_id']
        logger.info('patching API for {0}'.format(level_id))
        patch_url = '{0}/raw-level-instances/{1}'.format(API_ENDPOINT, level_id)
        response = dict()

        if level is None:
            return

        # patch level URL

        # FIXME - this is a temporary hack for Epitech's session
        response['private_urls'] = []
        response['private_urls'].append({'name': 'http', 'url': 'http://{0}:{1}/'.format(level.address, HTTP_LEVEL_PORT)})
        response['urls'] = []
        response['urls'].append({'name': 'http', 'url': 'http://{0}.levels.pathwar.net:80/'.format(api_level_instance['_id'])})

        # extract passphrases
        response['passphrases'] = level.passphrases

        headers = {
            'If-Match': api_level_instance['_etag'],
            'Content-Type': 'application/json',
        }

        r = requests.patch(patch_url, data=json.dumps(response), headers=headers)

    def api_fetch_level_instances(self):
        """ I fetch level instances from the API. """
        url = '{0}/{1}'.format(API_ENDPOINT, 'hypervisor-level-instances?embedded={"level":1}')
        r = requests.get(url)
        if r.status_code == 200:
            level_instances = []
            content = r.json()
            if '_items' in content:
                for item in content['_items']:
                    level_instances.append(item)
            return level_instances
        return []


if __name__ == '__main__':
    logger.setLevel(logging.INFO)
    if len(SENTRY_URL):
        LOGGING = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'console': {
                    'format': '[%(asctime)s][%(levelname)s] %(name)s %(filename)s:%(funcName)s:%(lineno)d | %(message)s',
                    'datefmt': '%H:%M:%S',
                },
            },

            'handlers': {
                'console': {
                    'level': 'DEBUG',
                    'class': 'logging.StreamHandler',
                    'formatter': 'console'
                },
                'sentry': {
                    'level': 'INFO',
                    'class': 'raven.handlers.logging.SentryHandler',
                    'dsn': SENTRY_URL,
                    'site': 'hypervisor',
                },
            },

            'loggers': {
                '': {
                    'handlers': ['console', 'sentry'],
                    'level': 'DEBUG',
                    'propagate': True,
                },
                'hypervisor': {
                    'handlers': ['console', 'sentry'],
                    'level': 'DEBUG',
                    'propagate': False,
                },
            }
        }
        logging.config.dictConfig(LOGGING)

    h = Hypervisor()
    h.loop()
