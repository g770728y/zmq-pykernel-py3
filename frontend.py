import pickle
import code
import readline
import sys
import time
import uuid

import zmq
import session
import completer


class Console(code.InteractiveConsole):
    def __init__(self, locals=None, filename="<console>",
                 session=session, request_socket=None,
                 sub_socket=None):
        code.InteractiveConsole.__init__(self, locals, filename)
        self.session = session
        self.request_socket = request_socket
        self.sub_socket = sub_socket
        self.backgrounded = 0
        self.messages = {}

        self.completer = completer.ClientCompleter(
            self, session, request_socket)
        readline.parse_and_bind("tab: complete")
        readline.parse_and_bind("set show-all-if-ambiguous on")
        readline.set_completer(self.completer.complete)

        sys.ps1 = "Py>>> "
        sys.ps2 = '  ... '
        sys.ps3 = "Out :"
        self.handlers = {}
        for msg_type in ["pyin", "pyout", "pyerr", "stream"]:
            self.handlers[msg_type] = getattr(self, "handle_%s" % msg_type)

    def handle_pyin(self, omsg):
        if omsg.parent_header.session == self.session.session:
            return

        c = omsg.content.code.rstrip()

        if c:
            print("[IN from %s]" % omsg.parent_header.username)
            print(c)

    def handle_pyout(self, omsg):
        if omsg.parent_hander.session == self.session.session:
            print("%s%s" % (sys.ps3, omsg.content.data))
        else:
            print("[Out from %s]" % omsg.parent_header.username)
            print(omsg.content.data)

    def print_pyerr(self, err):
        print(err.etype, ":", err.evalue, file=sys.stderr)
        print("".join(err.traceback), file=sys.stderr)

    def handle_pyerr(self, omsg):
        if omsg.parent_header.session == self.session.session:
            return
        print("[ERR from %s]" % omsg.parent_header.username)
        self.print_pyerr(omsg.content)

    def handle_stream(self, omsg):
        if omsg.content.name == "stdout":
            outstream = sys.stdout
        else:
            outstream = sys.stderr
            print("*ERR*", file=outstream)
        print(omsg.content.data, file=outstream)

    def handle_output(self, omsg):
        handler = self.handlers.get(omsg.msg_type, None)
        if handler is not None:
            handler(omsg)

    def recv_output(self):
        while True:
            omsg = self.session.recv(self.sub_socket)
            if omsg is None:
                break
            self.handle_output(omsg)

    def handle_reply(self, rep):
        self.recv_output()
        if rep is None:
            return
        if rep.content.status == "error":
            self.print_pyerr(rep.content)
        elif rep.content.status == "aborted":
            print("ERROR: ABORTED", file=sys.stderr)
            ab = self.messages[rep.parent_header.msg_id].content
            if "code" in ab:
                print(ab.code, file=sys.stderr)
            else:
                print(ab, file=sys.stderr)

    def recv_reply(self):
        rep = self.session.recv(self.request_socket)
        self.handle_reply(rep)
        return rep

    # 父类调用
    def runcode(self, code):
        src = "\n".join(self.buffer)

        if not src.endswith(";"):
            while self.backgrounded > 0:
                rep = self.recv_reply()
                if rep:
                    self.backgrounded -= 1
                time.sleep(0.05)

        omsg = self.session.send(
            self.request_socket, "execute_request", dict(code=src))
        self.messages[omsg.header.msg_id] = omsg

        if src.endswith(";"):
            self.backgrounded += 1
            return

        while True:
            rep = self.recv_reply()
            if rep is not None:
                break
            self.recv_output()
            time.sleep(0.05)


class InteractiveClient(object):
    def __init__(self, session, request_socket, sub_socket):
        self.session = session
        self.request_socket = request_socket
        self.sub_socket = sub_socket
        self.console = Console(None, "<zmq-console>",
                               session, request_socket, sub_socket)

    def interact(self):
        self.console.interact()


def main():
    ip = "127.0.0.1"
    port_base = 5555
    connection = ('tcp://%s' % ip) + ':%i'
    req_conn = connection % port_base
    sub_conn = connection % (port_base+1)

    c = zmq.Context()
    request_socket = c.socket(zmq.DEALER)
    request_socket.connect(req_conn)

    sub_socket = c.socket(zmq.SUB)
    sub_socket.connect(sub_conn)
    # ""表示订阅所有消息
    sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    sess = session.Session()
    client = InteractiveClient(sess, request_socket, sub_socket)

    client.interact()


if __name__ == "__main__":
    main()
