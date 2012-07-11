# coding: utf-8

#import cPickle as pickle
#from ctypes import *
#from _ctypes import *

from _cffi import C, ffi
from constants import *
from error import *
from utils import jsonapi

class Context(object):
    _state = {}
    def __init__(self, iothreads=1):
        if not iothreads > 0:
            raise ZMQError(EINVAL)

        self.__dict__ = self._state

        self.zmq_ctx = C.zmq_init(iothreads)
        self.iothreads = iothreads
        self._closed = False
        self.n_sockets = 0
        self.max_sockets = 32
        self._sockets = {}

    def term(self):
        for k, s in self._sockets.items():
            if not s.closed:
                s.close()
                self._rm_socket(k)
                self.n_sockets -= 1

        C.zmq_term(self.zmq_ctx)
        self.zmq_ctx = None
        self._closed = True

    @property
    def closed(self):
        return self._closed

    def _add_socket(self, socket):
        self._sockets[self.n_sockets] = socket
        self.n_sockets += 1

        return self.n_sockets

    def _rm_socket(self, n):
        del self._sockets[n]

    def socket(self, sock_type):
        if self._closed:
            raise ZMQError(ENOTSUP)

        return Socket(self, sock_type)

class Socket(object):
    def __init__(self, context, sock_type):
        self.context = context
        self.sock_type = sock_type
        self.zmq_socket = C.zmq_socket(context.zmq_ctx, sock_type)
        if not self.zmq_socket:
            raise ZMQError()
        self._closed = False
        self._attrs = {}
        self.n = self.context._add_socket(self)
        self.last_errno = None

    @property
    def closed(self):
        return self._closed

    def close(self):
        if not self._closed:
            C.zmq_close(self.zmq_socket)
            self._closed = True

    def bind(self, address):
        ret = C.zmq_bind(self.zmq_socket, address)
        return ret

    def connect(self, address):
        ret = C.zmq_connect(self.zmq_socket, address)
        return ret

    def send(self, message, flags=NOBLOCK):
        zmq_msg = ffi.new('zmq_msg_t')

        message = ffi.new('char[]', message)
        C.zmq_msg_init_data(zmq_msg, ffi.cast('void*', message), len(message),
                                                                 ffi.NULL,
                                                                 ffi.NULL)

        ret = C.zmq_send(self.zmq_socket, zmq_msg, flags)
        if ret < 0:
            self.last_errno = C.zmq_errno()
        return ret

    def recv(self, flags=0):
        zmq_msg = ffi.new('zmq_msg_t')
        C.zmq_msg_init(zmq_msg)
        ret = C.zmq_recv(self.zmq_socket, zmq_msg, flags)
        value = str(ffi.cast('char*', C.zmq_msg_data(zmq_msg)))
        if ret < 0:
            self.last_errno = C.zmq_errno()
        return value, ret


class Loop(object):
    def __init__(self, verbose=False):
        self.loop = czmq.zloop_new()
        if verbose:
            czmq.zloop_set_verbose(self.loop, c_bool(True))
        #self.callbacks = defaultdict(list)

    def start(self):
        rc = czmq.zloop_start(self.loop)
        return rc

    def timer(self, delay, times, function, socket):
        czmq.zloop_timer(self.loop,
                         c_size_t(delay),
                         c_size_t(times),
                         poller_callback_func(function),
                         c_void_p(socket.handle))

    def poller(self, item, event, socket):
        socket_handler = socket
        if hasattr(socket, 'handle'):
            socket_handler = socket.handle

        #self.callbacks[item].append(event)
        czmq.zloop_poller(self.loop,
                          pointer(item),
                          poller_callback_func(event),
                          socket_handler)

    def poller_end(self, item):
        #del self.callbacks[item]
        czmq.zloop_poller_end(self.loop,
                              pointer(item))

    def destroy(self):
        czmq.zloop_destroy(pointer(self.loop))

class ZFrame(object):
    '''
        zmq frame object
    '''
    def __init__(self, data=None):
        self._data = data
        if data:
            buffer = create_string_buffer(data)
            self.zframe = czmq.zframe_new(buffer,
                                          c_size_t(sizeof(buffer)))
        else:
            self.zframe = czmq.zframe_new(POINTER(c_int)(),
                                          c_ulong(0))

    def send(self, socket, flags):
        return czmq.zframe_send(pointer(self.zframe),
                                socket.handle,
                                c_int(flags))

    @property
    def data(self):
        return self._data

    @staticmethod
    def recv(socket):
        frame_ref = czmq.zframe_recv(socket.handle)
        str_data = czmq.zframe_data(frame_ref)
        return ZFrame(str_data)
