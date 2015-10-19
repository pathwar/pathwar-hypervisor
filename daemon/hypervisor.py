#!/usr/bin/env python

import argparse
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

from datetime import timedelta, datetime
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

    def load(self):
        self.pool.load()

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
        level_changed = level.source != api_level['url']
        level_redump = api_level['defaults']['redump']
        level_next_redump = level.dumped_at + timedelta(seconds=level_redump)
        level_need_redump = level_next_redump < datetime.now(level_next_redump.tzinfo)
        if level_changed or level_need_redump:
            logger.info('redumping level {0}'.format(level_id))
            self.pool.destroy_level(level_id)
            self.pool.create_level(level_id, api_level['url'])
            level = self.pool.get_level(level_id)
            self.api_update_level_instance(api_level_instance, level)
            return

    def force_redump(self, uuid):
        """ Used to force the redump of a level. """
        for api_level_instance in self.api_fetch_level_instances():
            if api_level_instance['_id'] == uuid:
                level_id = api_level_instance['_id']
                api_level = api_level_instance['level']

                # ignore level if incomplete
                if 'url' not in api_level or not api_level_instance['active']:
                    logger.debug('ignored level {0}'.format(level_id))
                    return

                logger.info('redumping level {0}'.format(level_id))
                self.pool.destroy_blindly(level_id)
                self.pool.create_level(level_id, api_level['url'])
                level = self.pool.get_level(level_id)
                self.api_update_level_instance(api_level_instance, level)

                return

        raise RuntimeError('level-instance {} not found'.format(uuid))

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

        r = requests.patch(patch_url, data=json.dumps(response), headers=headers, verify=False)

    def api_fetch_level_instances(self, resource=None):
        """ I fetch level instances from the API. """
        if not resource:
            resource = 'hypervisor-level-instances?embedded={"level":1}'
        url = '{0}/{1}'.format(API_ENDPOINT, resource)
        r = requests.get(url, verify=False)
        if r.status_code == 200:
            level_instances = []
            content = r.json()
            if '_items' in content:
                for item in content['_items']:
                    level_instances.append(item)
            if '_links' in content:
                try:
                    if 'next' in content['_links']:
                        next_resource = '{0}&embedded={{"level":1}}'.format(content['_links']['next']['href'])
                        level_instances.extend(self.api_fetch_level_instances(resource=next_resource))
                except:
                    pass
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
                    'level': 'WARNING',
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

    parser = argparse.ArgumentParser('Pathwar\'s hypervisor')
    parser.add_argument('action', type=str, choices=['loop', 'force-redump'], default='loop', help='action to perform')
    parser.add_argument('--uuid', type=str, help='uuid of the level instance to manipulate')
    args = parser.parse_args()

    if args.action == 'loop':
        h = Hypervisor()
        h.load()
        h.loop()
    elif args.action == 'force-redump':
        instance_uuid = args.uuid
        if not instance_uuid:
            raise RuntimeError('bad usage: missing instance uuid')
        h = Hypervisor()
        h.force_redump(instance_uuid)
