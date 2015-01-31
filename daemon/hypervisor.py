#!/usr/bin/env python

import requests
import json


API_ENDPOINT = 'http://root-token:@212.83.158.125:1337/level-instances?embedded={"level":1}'


class Hypervisor:

    """
    Hi, I'm the hypervisor:
    - I fetch levels
    - I dump levels
    - I notify the API
    - I sleep
    """

    def get_levels(self):
        r = requests.get(API_ENDPOINT)
        if r.status_code == 200:
            return r.json()['_items']
        return None

    def go(self):
        levels = self.get_levels()
        if levels:
            for level in levels:
                print level


if __name__ == '__main__':
    h = Hypervisor()
    h.go()
