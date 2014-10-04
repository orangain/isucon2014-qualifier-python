# coding: utf-8

from __future__ import print_function, unicode_literals

import sys
import time
import os.path

try:
    from cProfile import Profile
except ImportError:
    from profile import Profile

from pstats import Stats


class ProfilerMiddleware(object):

    def __init__(self, app, stream=None,
                 sort_by=('time', 'calls'), restrictions=(), profile_dir=None):
        self._app = app
        self._stream = stream or sys.stdout
        self._sort_by = sort_by
        self._restrictions = restrictions
        self._profile_dir = profile_dir
        self._pid = os.getpid()

    def __call__(self, environ, start_response):
        response_body = []

        def catching_start_response(status, headers, exc_info=None):
            start_response(status, headers, exc_info)
            return response_body.append

        def runapp():
            appiter = self._app(environ, catching_start_response)
            response_body.extend(appiter)
            if hasattr(appiter, 'close'):
                appiter.close()

        p = Profile()
        start = time.time()
        p.runcall(runapp)
        body = b''.join(response_body)
        end = time.time()
        elapsed = end - start

        if self._profile_dir is not None:
            prof_filename = os.path.join(
                self._profile_dir,
                '%s.%s.%06dms.%d.%f.%d.prof' % (
                    environ['REQUEST_METHOD'],
                    environ.get('PATH_INFO').strip('/').replace('/', '.') or 'root',
                    elapsed * 1000.0,
                    end,
                    self._pid,
                ))
            p.dump_stats(prof_filename)

        else:
            stats = Stats(p, stream=self._stream)
            stats.sort_stats(*self._sort_by)

            self._stream.write('-' * 80)
            self._stream.write('\nPATH: %r\n' % environ.get('PATH_INFO'))
            stats.print_stats(*self._restrictions)
            self._stream.write('-' * 80 + '\n\n')

        return [body]
