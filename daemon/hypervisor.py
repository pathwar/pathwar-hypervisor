#!/usr/bin/env python

class Hypervisor:
    """
    Hi, I'm the hypervisor:
    - I fetch levels
    - I dump levels
    - I notify the API
    - I sleep
    """

    def __init__(self):
        print("Hello World")

    def loop(self):
        pass

if __name__ == '__main__':
    h = Hypervisor()
    h.loop()
