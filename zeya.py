#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2009 Phil Sung, Samson Yeung, Romain Francoise
#
# This file is part of Zeya.
#
# Zeya is free software: you can redistribute it and/or modify it under the
# terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# Zeya is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Zeya. If not, see <http://www.gnu.org/licenses/>.


# Zeya - a web music server.

# Work with python2.5
from __future__ import with_statement

import os
import sys
import time
import StringIO
import threading
import bottle
from gzip_middleware import Gzipper

try:
    import json
    json.dumps
except (ImportError, AttributeError):
    import simplejson as json

import backends
import decoders
import options

class BadArgsError(Exception):
    """
    Error due to incorrect command-line invocation of this program.
    """
    def __init__(self, message):
        self.error_message = message
    def __str__(self):
        return "Error: %s" % (self.error_message,)

def get_backend(backend_type):
    """
    Return a backend object of the requested type.

    backend_type: string giving the backend type to use.
    """
    if backend_type == "rhythmbox":
        # Import the backend modules conditionally, so users don't have to
        # install dependencies unless they are actually used.
        from rhythmbox import RhythmboxBackend
        return RhythmboxBackend()
    elif backend_type == 'dir':
        from directory import DirectoryBackend
        return DirectoryBackend(path)
    elif backend_type == 'playlist':
        if path.lower().endswith('m3u'):
            from m3u import M3uBackend
            return M3uBackend(path)
        else:
            from pls import PlsBackend
            return PlsBackend(path)
    else:
        raise ValueError("Invalid backend %r" % (backend_type,))


@bottle.route('/getlibrary')
def web_getlibrary():
    header = {'Content-Type': 'text/html; charset=utf-8'}
    return bottle.conditionnal_response(library_repr, header=header,
                                        etag=library_etag)

@bottle.route('/getcontent')
def web_getcontent():
    key = bottle.request.params.get('key', '')
    buffered = bottle.request.params.get('buffered', False)
    bottle.response.content_type = 'audio/ogg'

    if buffered:
        output_file = StringIO.StringIO()
        backend.get_content(key, output_file, bitrate, buffered=True)
        output_file.seek(0)
        return output_file
    else:
        (read_end, write_end) = os.pipe()
        def backend_get_content():
            try:
                output_file = os.fdopen(write_end, 'wb')
                backend.get_content(key, output_file, bitrate)
            except IOError:
                pass
        threading.Thread(target=backend_get_content).start()
        return os.fdopen(read_end, 'rb')
    
@bottle.route('/')
@bottle.route('/:filename')
def web_static(filename='library.html'):
    return bottle.static_file(filename, root=resource_basedir)


if __name__ == '__main__':
    try:
        (show_help, backend_type, bitrate, bind_address, port, path, basic_auth_file) = \
            options.get_options(sys.argv[1:])
    except options.BadArgsError, e:
        print e
        options.print_usage()
        sys.exit(1)
    if show_help:
        options.print_usage()
        sys.exit(0)
    print "Using %r backend." % (backend_type,)
    try:
        backend = get_backend(backend_type)
    except IOError, e:
        print e
        sys.exit(1)
   
    # Read the library.
    print "Loading library..."

    library_contents = backend.get_library_contents()
    if not library_contents:
        print "Warning: no tracks were found. Check that you've specified " \
            + "the right backend/path."
    # Filter out songs that we won't be able to decode.
    filtered_library_contents = \
        [ s for s in library_contents \
              if decoders.has_decoder(backend.get_filename_from_key(s['key'])) ]
    if not filtered_library_contents and library_contents:
        print "Warning: no playable tracks were found. You may need to " \
            "install one or more decoders."

    try:
        playlists = backend.get_playlists()
    except NotImplementedError:
        playlists = None

    output = { 'library': filtered_library_contents,
               'playlists': playlists }

    library_repr = json.dumps(output, ensure_ascii=False)
    library_etag = str(time.time())
    
    basedir = os.path.abspath(os.path.dirname(os.path.realpath(sys.argv[0])))
    resource_basedir = os.path.join(basedir, 'resources')
    
    # Start up a web server.
    try:
        bottle.debug(True)
        bottle.run(host=bind_address or '0.0.0.0',
                   port=port,
                   app=Gzipper(bottle.app()),
                   server=bottle.PasteServer)
    except KeyboardInterrupt:
        pass
