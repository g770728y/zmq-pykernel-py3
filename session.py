import os
import uuid
import pprint
import unittest
import zmq


class Message():
    def __init__(self, msg_dict):
        dct = self.__dict__
        for k, v in msg_dict.items():
            if isinstance(v, dict):
                v = Message(v)
            dct[k] = v

    def __iter__(self):
        return iter(self.__dict__.items())

    def __repr__(self):
        return repr(self.__dict__)

    def __str__(self):
        return pprint.pformat(self.__dict__)

    def __contains__(self, k):
        return k in self.__dict__
    
    def __getitem__(self, k):
        return self.__dict__[k]

def msg_header(msg_id, username, session):
    return {
        'msg_id': msg_id,
        'username': username,
        'session': session,
    }

def extract_header(msg_or_header):
    if not msg_or_header:
        return {}
    try:
        h = msg_or_header['header']
    except KeyError:
        try:
            h = msg_or_header['msg_id']
        except KeyError:
            raise
        else:
            h = msg_or_header
    if not isinstance(h ,dict):
        h = dict(h)

    return h

class Session(object):
    def __init__(self, username=os.environ.get("USER", "username")):
      self.username = username
      self.session = str(uuid.uuid4())
      self.msg_id = 0
    
    def msg_header(self):
        h = msg_header(self.msg_id, self.username, self.session)
        self.msg_id += 1
        return h

    def msg(self, msg_type, content=None, parent=None):
        msg = {}
        msg['header'] = self.msg_header()
        msg['parent_header'] = {} if parent is None else extract_header(parent)
        msg['msg_type'] = msg_type
        msg['content'] = {} if content is None else content
        return msg

    def send(self, socket, msg_type, content=None, parent=None, ident=None):
      msg = self.msg(msg_type, content ,parent)
      if ident is not None: 
        socket.send(ident, zmq.SNDMORE)
      socket.send_json(msg) 
      omsg = Message(msg)
      return omsg

    def recv(self, socket, mode=zmq.NOBLOCK):
        try:
            msg = socket.recv_json(mode)
        except zmq.ZMQError as e:
            if e.errno == zmq.EAGAIN:
                return None
            else:
                raise
        return Message(msg)


class TestMsg(unittest.TestCase):
    def test1(self):
        am = dict(x=1)
        ao = Message(am)
        self.assertEqual(ao.x, am['x'])

        am['y'] = dict(z=1)
        ao = Message(am)
        self.assertEqual(ao.y.z, am['y']['z'])

        k1, k2 = 'y', 'z'
        self.assertEqual(ao[k1][k2], am[k1][k2])

        am2 = dict(ao)
        self.assertEqual(am['x'], am2['x'])
        self.assertEqual(am['y']['z'], am2['y']['z'])


if __name__ == '__main__':
    unittest.main()
