import sys
import time
import traceback
import builtins

import zmq

from session import Session, Message, extract_header
from completer import KernelCompleter


class OutStream(object):
    """A file like object that published the stream to a zMQ PUB socket."""

    def __init__(self, session, pub_socket, name, max_buffer=200):
        self.session = session
        self.pub_socket = pub_socket
        self.name = name
        self._buffer = []
        self._buffer_len = 0
        self.max_buffer = max_buffer
        self.parent_header = {}

    def set_parent(self, parent):
        self.parent_header = extract_header(parent)

    def close(self):
        self.pub_socket = None

    def flush(self):
        if self.pub_socket is None:
            raise ValueError("I/O operation on closed file")
        else:
            if self._buffer:
                data = "".join(self._buffer)
                content = {"name": self.name, "data": data}
                msg = self.session.msg(
                    "stream", content=content, parent=self.parent_header)
                print(Message(msg), file=sys.__stdout__)
                self.pub_socket.send_json(msg)
                self._buffer_len = 0
                self._buffer = []

    def isattr(self):
        return False

    def next(self):
        raise IOError("Read not supprted on a write only stream")

    def read(self):
        raise IOError("Read not supprted on a write only stream")

    readline = read

    def write(self, s):
        if self.pub_socket is None:
            raise ValueError("I/O operation on closed file")

        else:
            self._buffer.append(s)
            self._buffer_len += len(s)
            self._maybe_send()

    def _maybe_send(self):
        if "\n" in self._buffer[-1]:
            self.flush()

        if self._buffer_len > self.max_buffer:
            self.flush()

    def writelines(self, sequence):
        if self.pub_socket is None:
            raise ValueError("I/O operation on closed file")
        else:
            for s in sequence:
                self.write(s)


class DisplayHook(object):
    def __init__(self, session, pub_socket):
        self.session = session
        self.pub_socket = pub_socket
        self.parent_header = {}

    def __call__(self, obj):
        if obj is None:
            return

        builtins._ = obj
        msg = self.session.msg(
            "pyout", {"data": repr(obj)}, parent=self.parent_header)
        self.pub_socket.send_json(msg)

    def set_parent(self, parent):
        self.parent_header = extract_header(parent)

class RawInput(object):
    def __init__(self, session, socket):
        self.session = session
        self.socket = socket

    def __call__(self, prompt=None):
        msg = self.session.msg("raw_input")
        self.socket.send_json(msg)
        while True:
            try:
                reply = self.socket.recv_json(zmq.NOBLOCK)
            except zmq.ZMQError as e:
                if e.errno == zmq.EAGAIN:
                    pass
                else:
                    raise
            else:
                break
        return reply["content"]["data"]

class Kernel(object):
    def __init__(self, session, reply_socket, pub_socket):
        self.session = session
        self.reply_socket = reply_socket
        self.pub_socket = pub_socket
        self.user_ns = {}
        self.history = []
        self.completer = KernelCompleter(self.user_ns)

        self.handlers = {}
        for msg_type in ["execute_request", "complete_request"]:
            self.handlers[msg_type] = getattr(self, msg_type)

    def abort_queue(self):
        while True:
            try:
                ident = self.reply_socket.recv(zmq.NOBLOCK)
            except zmq.ZMQError as e:
                if e.errno == zmq.EAGAIN:
                    break
            else:
              msg = self.reply_socket.recv_json()

            print("Aborting:", file=sys.__stdout__)
            print(Message(msg), file=sys.__stdout__)

            msg_type = msg["msg_type"]
            reply_type = msg_type.split("_")[0] + "_reply"
            reply_msg = self.session.msg(reply_type, {"status": "aborted"}, msg)
            print(Message(reply_msg), sys.__stdout__)
            self.reply_socket.send(ident, zmq.SNDMORE)
            self.reply_socket.send_json(reply_msg)
            time.sleep(0.1)

    def execute_request(self, ident, parent):
        try: 
            code = parent["content"]["code"]
        except:
            print("Got bad msg:", file=sys.__stderr__)
            print(Message(parent), file=sys.__stderr__)
            return
        pyin_msg = self.session.msg("pyin", {"code": code}, parent=parent)
        self.pub_socket.send_json(pyin_msg)

        try: 
            comp_code = compile(code, "<zmq-kernel>", "exec")
            sys.displayhook.set_parent(parent)
            exec(comp_code, self.user_ns, self.user_ns) 
        except:
            result = "error"
            etype, evalue, tb = sys.exc_info()
            tb = traceback.format_exception(etype, evalue, tb)
            exc_content = {
                "status": "error",
                "traceback": tb,
                "etype": etype,
                "evalue": evalue,
            }
            exc_msg = self.session.msg("pyerr", exc_content, parent)
            self.pub_socket.send_json(exc_msg)
            reply_content = exc_content
        else:
            reply_content = {"status": "ok"}
        
        reply_msg = self.session.msg("execute_reply", reply_content, parent)
        print(Message(reply_msg), file=sys.__stdout__)
        self.reply_socket.send(ident, zmq.SNDMORE)
        self.reply_socket.send_json(reply_msg)
        if reply_msg["content"]["status"] == "error":
            self.abort_queue()

    def complete_request(self, ident, parent):
        matches = {"matches": self.complete(parent), "status": "ok"}
        completion_msg = self.session.send(self.reply_socket, "complete_reply", matches,parent, ident)
        print("completion:", completion_msg, file=sys.__stdout__)

    def complete(self, msg):
        return self.completer.complete(msg.content.line, msg.content.text)
    
    def start(self):
        while True:
            ident = self.reply_socket.recv()
            msg = self.reply_socket.recv_json()
            omsg = Message(msg)
            print(omsg, file=sys.__stdout__)
            handler = self.handlers.get(omsg.msg_type, None)
            if handler is None:
                print("UNKNOWN MESSAGE TYPE:", omsg, file=sys.__stderr__)
            else:
                handler(ident, omsg)

def main():
    c = zmq.Context()
    ip = "127.0.0.1"
    port_base = 5555
    connection = ("tcp://%s" % ip) + ":%i"
    rep_conn = connection % port_base
    pub_conn =  connection % (port_base + 1)

    print("Starting the kernel...", file=sys.__stdout__)
    print("On:", rep_conn, pub_conn, file=sys.__stdout__)

    session = Session(username="kernel")

    reply_socket = c.socket(zmq.ROUTER)
    reply_socket.bind(rep_conn)

    pub_socket = c.socket(zmq.PUB)
    pub_socket.bind(pub_conn)

    stdout = OutStream(session, pub_socket, "stdout")
    stderr = OutStream(session, pub_socket, "stderr")
    sys.stdout = stdout
    sys.stderr = stderr

    # 比较stdout与display_hook
    # sys.displayhook 用于修改 Python 返回值的输出方式，而 sys.stdout 用于控制程序输出的位置和方式。
    # 比如 你想将输出+1, 或写入远程socket, 可以使用displayhook
    display_hook = DisplayHook(session, pub_socket)
    # displayhook用于回显结果，这里将回显重定向到 pyout类型的msg后输出
    sys.displayhook = display_hook

    kernel = Kernel(session, reply_socket, pub_socket)

    kernel.user_ns["sleep"] = time.sleep
    kernel.user_ns["s"] = "Test string"

    print("Use Ctrl-\\ (Not Ctrl-C!) to terminate.", sys.__stdout__)

    kernel.start()

if __name__ == "__main__":
    main()
