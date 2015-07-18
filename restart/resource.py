from __future__ import absolute_import

from werkzeug.utils import import_string

from .config import config
from .exceptions import HTTPException
from .response import Response


class Resource(object):
    """The core class that represents a REST resource.

    :param action_map: the mapping of request methods to resource actions.
    """

    #: The name of the resource.
    name = None

    #: The class used for parser objects.
    parser_class = import_string(config.PARSER_CLASS)

    #: The class used for parser objects.
    renderer_class = import_string(config.RENDERER_CLASS)

    def __init__(self, action_map):
        self.action_map = action_map

    @property
    def logger(self):
        """A :class:`logging.Logger` object for this API."""
        from .logging import global_logger
        return global_logger

    def _get_head(self):
        """Get the head message for logging."""
        query_string = self.request.environ['QUERY_STRING']
        separator = '?' if query_string else ''
        head = '[%s %s%s%s]' % (self.request.method, self.request.path,
                                separator, query_string)
        return head

    def log_message(self, msg):
        """Logs a message with `DEBUG` level.

        :param msg: the message to be logged.
        """
        if self.request.method in config.LOGGER_METHODS:
            self.logger.debug('%s %s' % (self._get_head(), msg))

    def log_exception(self, exc):
        """Logs an exception with `ERROR` level.

        :param exc: the exception to be logged.
        """
        self.logger.exception('Exception on %s' % self._get_head())

    def dispatch_request(self, request, *args, **kwargs):
        """Does the request dispatching. Matches the HTTP method and return
        the return value of the bound action.

        :param request: the request object.
        :param args: the positional arguments captured from the URI.
        :param kwargs: the keyword arguments captured from the URI.
        """
        try:
            action_name = self.action_map[request.method]
        except KeyError as exc:
            exc.args = (
                'Config `ACTION_MAP` has no mapping for %r' % request.method,
            )
            raise

        try:
            action = getattr(self, action_name)
        except AttributeError as exc:
            exc.args = ('Unimplemented action %r' % action_name,)
            raise

        self.request = request.parse(self.parser_class)
        self.log_message('<Request> %s' % request.data)

        try:
            rv = action(request, *args, **kwargs)
        except Exception as exc:
            rv = self.handle_exception(exc)

        response = self.make_response(rv)
        self.log_message('<Response> %s %s' % (response.status, response.data))

        return response.render(self.renderer_class)

    def handle_exception(self, exc):
        """Handle any exception that occurs, by returning an appropriate
        response, or re-raising the error.

        :param exc: the exception to be handled.
        """
        if isinstance(exc, HTTPException):
            headers = dict(exc.get_headers(self.request.environ))
            rv = ({'message': exc.description}, exc.code, headers)
            return rv
        else:
            self.log_exception(exc)
            raise exc

    def make_response(self, rv):
        """Converts the return value to a real response object that is
        an instance of :class:`~restart.response.Response`.

        The following types are allowed for `rv`:

        ======================  ============================================
        :class:`Response`       the object is returned unchanged
        :class:`str`            the string becomes the response body
        :class:`unicode`        the unicode string becomes the response body
        :class:`tuple`          A tuple in the form ``(data, status)``
                                or ``(data, status, headers)`` where
                                `data` is the response body, `status` is
                                an integer and `headers` is a dictionary
                                with header values.
        ======================  ============================================
        """
        status = 200
        headers = None

        if isinstance(rv, tuple):
            rv_len = len(rv)
            if rv_len == 2:
                rv, status = rv
            elif rv_len == 3:
                rv, status, headers = rv
            else:
                raise ValueError('Resource action return a wrong response')

        if rv is None:
            raise ValueError('Resource action did not return a response')
        elif not isinstance(rv, Response):
            rv = Response(rv, status=status, headers=headers)

        return rv
