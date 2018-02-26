#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2016 confirm IT solutions
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import os
import sys
import yaml
import json
import re
from subprocess import check_call
from argparse import ArgumentParser
from tempfile import mkdtemp
from shutil import rmtree
from ansible.constants import p, get_config
from ansible import utils

class AnsibleGitInventory(object):
    '''
    Class to read a YAML from a git repository and generate a valid Ansible
    dynamic inventory output.

    Please use this class within a with-block or call the cleanup() method
    manually when you're finished.
    '''

    def __init__(self):
        '''
        Class constructor which creates the temporary working directory.
        '''
        self.working_dir = mkdtemp()

    def __enter__(self):
        '''
        Returns the instance pointer when with-context is entered.
        '''
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        '''
        Wrapper to call cleanup() when with-context is exited.
        '''
        self.cleanup()

    def cleanup(self):
        '''
        Removes the temporary working directory and therefor all generated
        data on the filesystem.
        '''
        if os.path.isdir(self.working_dir):
            rmtree(self.working_dir)

    def clone_repository(self, url, commit=None, sshkey=None):
        '''
        Clone git repository into a temporary working directory.

        To specify a specific commit branch or tag you can use the `commit`
        argument. If you want to use an alternative SSH key define the
        `sshkey` argument.
        '''
        if sshkey:
            os.environ['GIT_SSH_COMMAND'] = 'ssh -i ' + sshkey

        command = ['git', 'clone', '-q']

        if commit:
            command.extend(['-b', commit])

        command.append(url)
        command.append(self.working_dir)

        check_call(command)

    def parse_inventory(self, path):

        inventory = os.path.join(self.working_dir, path)
        name      = os.path.basename(inventory).split('.')[0]

        if not os.path.isfile(inventory):
            raise IOError('Inventory file "{}" not found in repository'.format(path))

        # Read inventory file.
        with open(inventory, 'r') as f:
            # Parse YAML.
            data = yaml.load(f)

            result = {}
            for group, groupdata in data.iteritems():
		groupobj = {}
                # Check for host definition. Could be absend due to
                # child definition
                if ('hosts' in groupdata) and (groupdata['hosts'] is not None):
                    hosts = groupdata['hosts']
                    hostobj = []

                    for host in hosts:
                        if type(host) is dict:
                            #we have host-level vars to deal with
                            hostname = host.keys()[0]
                            hostvars = host[hostname]
                            hostobj.append(hostname)
                            #test if result obj has the _meta thingy
                            if not '_meta' in result.keys():
                                result['_meta'] = {}
                                result['_meta']['hostvars'] = {}

                            result['_meta']['hostvars'][hostname] = hostvars
                        else:
                            #just add the host
                            hostobj.append(host)
                    groupobj['hosts'] = hostobj

                if ('vars' in groupdata) and (groupdata['vars'] is not None):
                    vars = {}
                    variables = groupdata['vars']
                    for var in variables:
                        key = var.keys()[0]
                        value = var[key]
                        vars[key] = value

                    groupobj['vars'] = vars

                if ('children' in groupdata) and (groupdata['children'] is not None):
                    childobj = []
                    children = groupdata['children']
                    for var in children:
                        childobj.append(var)

                    groupobj['children'] = childobj

                result[group] = groupobj

            return json.dumps(obj=result, sort_keys=True, indent=4, separators=(',', ': '))


if __name__ == '__main__':

    #
    # Get arguments from CLI or via environment variables.
    #
    # We need to do that because the Tower can't pass any CLI arguments to a
    # dynamic inventory script. Therefor environment variables must be used.
    #

    if 'DEBUG_TEST_PATH' in os.environ:
        debug_test_path = os.environ['DEBUG_TEST_PATH']
        with AnsibleGitInventory() as obj:
            data = obj.parse_inventory(path=debug_test_path)
            print(data)


    if 'URL' in os.environ and 'INVENTORY' in os.environ and os.environ['URL'] and os.environ['INVENTORY']:

        kwargs_clone = {
            'url': os.environ['URL'],
        }

        inventory = os.environ['INVENTORY']

        if 'SSHKEY' in os.environ:
            kwargs_clone['sshkey'] = os.environ['SSHKEY']

        if 'COMMIT' in os.environ:
            kwargs_clone['commit'] = os.environ['COMMIT']
    
    else:
        #Read things from ansible config
        config_section = "git-inventory"
        url = get_config(p, config_section, "url", "URL","")
        sshkey = get_config(p, config_section, "sshkey", "SSHKEY","")
        commit = get_config(p, config_section, "commit", "COMMIT","")
        inventory = get_config(p, config_section, "inventory", "INVENTORY","")

        kwargs_clone = {
            'url': url,
            'sshkey': sshkey,
            'commit': commit,
        }

#    else:
#
#        # Parse CLI arguments.
#        parser = ArgumentParser(description='Ansible inventory script')
#        parser.add_argument('--sshkey', help='Path to an alternative SSH private key', type=str)
#        parser.add_argument('--commit', help='Commit to checkout (e.g. branch or tag)', type=str)
#        parser.add_argument('url', help='URL of the git repository', type=str)
#        parser.add_argument('inventory', help='Path of the inventory file', type=str)
#        args = parser.parse_args()
#
#        kwargs_clone = {
#            'url': args.url,
#            'sshkey': args.sshkey,
#            'commit': args.commit,
#        }
#
#        inventory = args.inventory

    #
    # Clone repository and parse inventory file.
    #

    try:

        with AnsibleGitInventory() as obj:

            # Clone repository.
            obj.clone_repository(**kwargs_clone)

            # Parse inventory.
            data = obj.parse_inventory(path=inventory)

        # Print inventory JSON and exit.
        sys.stdout.write(data + '\n')
        sys.stdout.flush()
        sys.exit(0)

    except Exception, e:
        sys.stderr.write(str(e) + '\n')
        sys.stderr.flush()
        sys.exit(1)
