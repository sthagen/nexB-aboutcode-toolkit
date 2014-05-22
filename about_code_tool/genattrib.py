#!/usr/bin/env python
# -*- coding: utf8 -*-

"""
This is a tool to generate component attribution based on a set of .ABOUT files.
Optionally, one could pass a subset list of specific components for set of
.ABOUT files to generate attribution.
"""

from __future__ import print_function
from __future__ import with_statement
from about import AboutCollector
import genabout

import codecs
import csv
import errno
import fnmatch
import getopt
import httplib
import logging
import optparse
import posixpath
import socket
import string
import sys
import urlparse

from collections import namedtuple
from datetime import datetime
from email.parser import HeaderParser
from os import listdir, walk
from os.path import exists, dirname, join, abspath, isdir, basename, normpath
from StringIO import StringIO

LOG_FILENAME = 'error.log'

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setLevel(logging.CRITICAL)
handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
logger.addHandler(handler)
file_logger = logging.getLogger(__name__+'_file')

__version__ = '0.9.0'

__about_spec_version__ = '0.8.0'  # See http://dejacode.org

__copyright__ = """
Copyright (c) 2013-2014 nexB Inc. All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

def component_subset_to_sublist(input_list):
    sublist = []
    sublist = [row["about_file"] for row in input_list
                   if "about_file" in row.keys()]
    return sublist

def update_path_to_about(input_list):
    output_list = []
    for row in input_list:
        if row.endswith('/'):
            row = row.rpartition('/')[0]
        output_list.append(row + '.ABOUT')
    return output_list

USAGE_SYNTAX = """\
    Input can be a file or directory.
    Output of rendered template must be a file (e.g. .html).
    Component List must be a .csv file which has at least an "about_resource" column.
"""

VERBOSITY_HELP = """\
Print more or fewer verbose messages while processing ABOUT files
0 - Do not print any warning or error messages, just a total count (default)
1 - Print error messages
2 - Print error and warning messages
"""

MAPPING_HELP = """\
Configure the mapping key from the MAPPING.CONFIG
"""

def main(parser, options, args):
    overwrite = options.overwrite
    verbosity = options.verbosity
    mapping_config = options.mapping
    
    if options.version:
        print('ABOUT tool {0}\n{1}'.format(__version__, __copyright__))
        sys.exit(0)

    if verbosity == 1:
        handler.setLevel(logging.ERROR)
    elif verbosity >= 2:
        handler.setLevel(logging.WARNING)

    if mapping_config:
        if not exists('MAPPING.CONFIG'):
            print("The file 'MAPPING.CONFIG' does not exist.")
            sys.exit(errno.EINVAL)

    if not len(args) == 3:
        print('Path for input, output and component list are required.\n')
        parser.print_help()
        sys.exit(errno.EEXIST)

    input_path, output_path, component_subset_path = args

    # TODO: need more path normalization (normpath, expanduser)
    # input_path = abspath(input_path)
    output_path = abspath(output_path)

    # Add the following to solve the 
    # UnicodeEncodeError: 'ascii' codec can't encode character
    reload(sys)
    sys.setdefaultencoding('utf-8')

    if not exists(input_path):
        print('Input path does not exist.')
        parser.print_help()
        sys.exit(errno.EEXIST)

    if isdir(output_path):
        print('Output must be a file, not a directory.')
        parser.print_help()
        sys.exit(errno.EISDIR)

    if exists(output_path) and not overwrite:
        print('Output file already exists. Select a different file name or use '
              'the --overwrite option.')
        parser.print_help()
        sys.exit(errno.EEXIST)

    if component_subset_path and not exists(component_subset_path):
        print('Component Subset path does not exist.')
        parser.print_help()
        sys.exit(errno.EEXIST)

    if not exists(output_path) or (exists(output_path) and overwrite):
        collector = AboutCollector(input_path)
        input_list = []
        if not component_subset_path:
            sublist = None
        else:
            with open(component_subset_path, "rU") as f:
                input_dict = csv.DictReader(f)
                for row in input_dict:
                    # Force the path to start with the '/' to do the mapping
                    # with the project structure
                    if not row['about_file'].startswith('/'):
                        row['about_file'] = '/' + row['about_file']
                    input_list.append(row)
            if mapping_config:
                mapping_list = genabout.GenAbout().get_mapping_list()
                input_list = genabout.GenAbout().convert_input_list(input_list, mapping_list)
            sublist = component_subset_to_sublist(input_list)
            outlist = update_path_to_about(sublist)

        attrib_str = collector.generate_attribution( limit_to = outlist )
        with open(output_path, "w") as f:
            f.write(attrib_str)
        errors = collector.get_genattrib_errors()

        # Clear the log file
        with open(join(dirname(output_path), LOG_FILENAME), 'w'):
            pass
    
        file_handler = logging.FileHandler(join(dirname(output_path), LOG_FILENAME))
        file_logger.addHandler(file_handler)
        for error_msg in errors:
                logger.error(error_msg)
                file_logger.error(error_msg)
    else:
        # we should never reach this
        assert False, "Unsupported option(s)."

def get_parser():
    class MyFormatter(optparse.IndentedHelpFormatter):
        def _format_text(self, text):
            """
            Overridden to allow description to be printed without
            modification
            """
            return text

        def format_option(self, option):
            """
            Overridden to allow options help text to be printed without
            modification
            """
            result = []
            opts = self.option_strings[option]
            opt_width = self.help_position - self.current_indent - 2
            if len(opts) > opt_width:
                opts = "%*s%s\n" % (self.current_indent, "", opts)
                indent_first = self.help_position
            else:                       # start help on same line as opts
                opts = "%*s%-*s  " % (self.current_indent, "", opt_width, opts)
                indent_first = 0
            result.append(opts)
            if option.help:
                help_text = self.expand_default(option)
                help_lines = help_text.split('\n')
                result.append("%*s%s\n" % (indent_first, "", help_lines[0]))
                result.extend(["%*s%s\n" % (self.help_position, "", line)
                               for line in help_lines[1:]])
            elif opts[-1] != "\n":
                result.append("\n")
            return "".join(result)

    parser = optparse.OptionParser(
        usage='%prog [options] input_path output_path component_list',
        description=USAGE_SYNTAX,
        add_help_option=False,
        formatter=MyFormatter(),
    )
    parser.add_option("-h", "--help", action="help", help="Display help")
    parser.add_option("-v", "--version", action="store_true",
        help='Display current version, license notice, and copyright notice')
    parser.add_option('--overwrite', action='store_true',
                      help='Overwrites the output file if it exists')
    parser.add_option('--verbosity', type=int, help=VERBOSITY_HELP)
    parser.add_option('--mapping', action='store_true', help=MAPPING_HELP)
    return parser


if __name__ == "__main__":
    parser = get_parser()
    options, args = parser.parse_args()
    main(parser, options, args)
