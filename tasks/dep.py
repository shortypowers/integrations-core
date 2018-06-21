# (C) Datadog, Inc. 2010-2017
# All rights reserved
# Licensed under Simplified BSD License (see LICENSE)
from __future__ import print_function, unicode_literals

import os
import re
from collections import defaultdict
from io import open

from invoke import task
from invoke.exceptions import Exit
from six import iteritems

from .constants import ROOT


DEP_PATTERN = re.compile(r'^([^=]+)==(\S+)')


def ensure_deps_declared(reqs_txt, reqs_in):
    if os.path.isfile(reqs_txt) and not os.path.isfile(reqs_in):
        declacred_lines = []

        with open(reqs_txt, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for line in lines:
            line = line.split('--hash')[0].strip('\r\n \\')
            if line and not line.startswith('#'):
                declacred_lines.append(line + '\n')

        with open(reqs_in, 'w', encoding='utf-8') as f:
            f.writelines(declacred_lines)


@task
def dep_check(ctx):
    packages = defaultdict(lambda: defaultdict(list))

    for check_name in sorted(os.listdir(ROOT)):
        reqs_file = os.path.join(ROOT, check_name, 'requirements.in')
        if os.path.isfile(reqs_file):
            with open(reqs_file, 'r') as f:
                for line in f:
                    match = DEP_PATTERN.match(line)
                    if match:
                        package, version = match.groups()
                        packages[package.lower()][version].append(check_name)

    output = ''
    for package, versions in sorted(iteritems(packages)):
        if len(versions) > 1:
            output += 'Multiple versions found for package `{}`:\n'.format(package)
            for version, checks in sorted(iteritems(versions)):
                if len(checks) == 1:
                    output += '    {}: {}\n'.format(version, checks[0])
                elif len(checks) == 2:
                    output += '    {}: {} and {}\n'.format(version, checks[0], checks[1])
                else:
                    remaining = len(checks) - 2
                    output += '    {}: {}, {}, and {} other{}\n'.format(
                        version,
                        checks[0],
                        checks[1],
                        remaining,
                        's' if remaining > 1 else ''
                    )

    if output:
        print(output[:-1])
        Exit(1)


@task(help={
    'package': 'The package to upgrade throughout the integrations',
    'version': 'The version of the package to pin',
    'verbose': 'Whether or not to produce output',
})
def dep_upgrade(ctx, package=None, version=None, verbose=False):
    """Upgrade a dependency for all integrations that require it.
    ``pip-compile`` must be in PATH.

    Example invocation:
        inv upgrade --verbose -p=requests -v=2.18.4
    """
    if not (package and version):
        raise Exit('`package` and `version` are required arguments.')

    for check_name in sorted(os.listdir(ROOT)):
        check_dir = os.path.join(ROOT, check_name)
        reqs_in = os.path.join(check_dir, 'requirements.in')
        reqs_txt = os.path.join(check_dir, 'requirements.txt')

        ensure_deps_declared(reqs_txt, reqs_in)

        if os.path.isfile(reqs_in):
            with open(reqs_in, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                try:
                    pkg = line.split('=')[0].strip()
                    if pkg == package:
                        break
                except IndexError:
                    continue
            # Skip integrations that don't require the package.
            else:
                continue

            if verbose:
                print('Check `{}`:'.format(check_name))
                print('    Old: `{}`'.format(lines[i].strip()))

            lines[i] = '{}=={}\n'.format(package, version)

            with open(reqs_in, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            if verbose:
                print('    New: `{}`'.format(lines[i].strip()))
                print('    Locking dependencies...')

            with ctx.cd(check_dir):
                ctx.run(
                    'pip-compile '
                    '--upgrade '
                    '--generate-hashes '
                    '--output-file requirements.txt '
                    'requirements.in',
                    hide='both'
                )
