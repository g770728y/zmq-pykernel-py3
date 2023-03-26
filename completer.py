from __future__ import print_function

import itertools
import readline
import rlcompleter
import time
import session

class KernelCompleter(object):
    """kernel-side completion machinery"""
    def __init__(self,namespace):
        self.namespace = namespace
        self.completer = rlcompleter.Completer(namespace)

    def complete(self, line, text):
        matches = []
        complete = self.completer.complete
        for state in itertools.count():
            comp = complete(text, state)
            if comp is None:
                break
            matches.append(comp)
        return matches

class ClientCompleter(object):
    """Client-side completion machinery"""
    def __init__(self, client, session, socket):
        self.client = client
        self.session = session
        self.socket = socket
        self.matches = []

    def request_completion(self, text):
        line = readline.get_line_buffer()
        msg = self.session.send(self.socket, 'complete_request', dict(text=text, line=line))

        for i in range(5):
            rep = self.session.recv(self.socket)
            if rep is not None and rep.msg_type == 'complete_reply':
                matches = rep.content.matches
                break
            time.sleep(0.1)
        else:
            print("TIMEOUT")
            matches = None

        return matches

    def complete(self, text, state):
      if self.client.backgrounded > 0:
          print("\n[Not completing, background tasks active]")
          print(readline.get_line_buffer(), end='')
          return None
        
      if state == 0:
          matches = self.request_completion(text)
          if matches is None:
              self.matches = []
              print("WARNING: Kernel timeout on tab completion.")

          else:
              self.matches = matches
          
      try:
          return self.matches[state]
      except IndexError:
          return None