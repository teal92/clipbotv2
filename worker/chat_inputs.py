"""Ephemeral receive-only Twitch chat cues; Kick requires verified webhooks.

Anonymous IRC is best-effort, not a currently documented authentication contract.
No viewer messages are sent, stored, or logged by this module.
"""
import re
import secrets
import socket
import ssl
import certifi
import threading
import time

MAX_LINE_BYTES = 8192
MAX_MESSAGE_CHARS = 500
_LOGIN = re.compile(r"[a-z0-9_]{1,25}\Z")


def validated_login(value):
    if not isinstance(value, str) or not _LOGIN.fullmatch(value.lower()):
        raise ValueError("Invalid channel login")
    return value.lower()


def parse_privmsg(line, channel):
    """Return only bounded message text for the requested room, never identity."""
    channel = validated_login(channel)
    if len(line.encode('utf-8')) > MAX_LINE_BYTES or '\r' in line or '\n' in line:
        return None
    if line.startswith('@'):
        _, separator, line = line.partition(' ')
        if not separator:
            return None
    if not line.startswith(':'):
        return None
    prefix, separator, rest = line.partition(' ')
    if not separator or '!' not in prefix:
        return None
    command, separator, rest = rest.partition(' ')
    target, trailing, message = rest.partition(' :')
    if command != 'PRIVMSG' or not separator or target.lower() != '#' + channel or not trailing:
        return None
    return message[:MAX_MESSAGE_CHARS] if message else None


class ChatWatcher:
    """Run in a caller-owned thread. Callback receives message text only.

    Three connection attempts per run; TLS certificate verification is enabled.
    `connected` means the server confirmed channel join, not merely TCP connect.
    Stop events interrupt receive within one second; close() interrupts immediately.
    """
    def __init__(self, source, on_message, stop_event, authentication=None):
        self.authentication=authentication
        if authentication is not None and (not isinstance(authentication,tuple) or len(authentication)!=2 or not isinstance(authentication[1],str) or not 1<=len(authentication[1])<=16000 or any(c in authentication[1] for c in '\r\n')):raise ValueError('Invalid chat authentication')
        if authentication is not None:validated_login(authentication[0])
        self.platform = source.get('platform')
        from .capture import stream_url
        stream_url(source)
        self.login = validated_login(source.get('login')) if self.platform=='twitch' else source['login'].lower()
        self.on_message = on_message
        self.stop_event = stop_event
        self.status = 'unavailable'
        self._socket = None
        self._closed = threading.Event()

    def close(self):
        self._closed.set()
        connection = self._socket
        if connection is not None:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        self.status = 'unavailable'

    def _stopped(self):
        return self.stop_event.is_set() or self._closed.is_set()

    def _backoff(self, seconds):
        deadline = time.monotonic() + seconds
        while not self._stopped() and time.monotonic() < deadline:
            self._closed.wait(min(.1, max(0, deadline - time.monotonic())))

    def run(self):
        if self.platform != 'twitch' or self._stopped():
            return
        for attempt in range(3):
            if self._stopped():
                break
            self.status = 'connecting'
            try:
                self._receive()
            except (OSError, ValueError):
                pass
            finally:
                connection, self._socket = self._socket, None
                if connection is not None:
                    connection.close()
                self.status = 'unavailable'
            if attempt < 2:
                self._backoff(2 ** attempt)

    def _receive(self):
        raw = socket.create_connection(('irc.chat.twitch.tv', 6697), timeout=5)
        self._socket = raw
        try:
            connection = ssl.create_default_context(cafile=certifi.where()).wrap_socket(raw, server_hostname='irc.chat.twitch.tv')
        except BaseException:
            raw.close()
            raise
        self._socket = connection
        connection.settimeout(1)
        nickname = self.authentication[0] if self.authentication else 'justinfan' + str(secrets.randbelow(900000000) + 100000000)
        auth='PASS oauth:'+self.authentication[1]+'\r\n' if self.authentication else ''
        connection.sendall((auth+'NICK ' + nickname + '\r\nJOIN #' + self.login + '\r\n').encode('ascii'))
        buffer = b''
        join_deadline = time.monotonic() + 15
        while not self._stopped():
            if self.status != 'connected' and time.monotonic() > join_deadline:
                return
            try:
                chunk = connection.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                return
            buffer += chunk
            while b'\r\n' in buffer:
                encoded, buffer = buffer.split(b'\r\n', 1)
                if len(encoded) > MAX_LINE_BYTES:
                    raise ValueError('IRC line limit exceeded')
                line = encoded.decode('utf-8', errors='replace')
                if line.startswith('PING :'):
                    connection.sendall(('PONG ' + line[5:] + '\r\n').encode('utf-8'))
                elif ' RECONNECT' in line or ' NOTICE ' in line:
                    return
                elif (line.startswith(':' + nickname + '!') and line.endswith(' JOIN #' + self.login)) or (' 366 ' + nickname + ' #' + self.login + ' :' in line):
                    self.status = 'connected'
                else:
                    message = parse_privmsg(line, self.login)
                    if message is not None and self.status == 'connected':
                        self.on_message(message)
            if len(buffer) > MAX_LINE_BYTES:
                raise ValueError('IRC buffer limit exceeded')
