import threading
from unittest.mock import Mock
import pytest
from worker.chat_inputs import ChatWatcher, parse_privmsg, validated_login, MAX_MESSAGE_CHARS


def test_login_validation_prevents_irc_command_injection():
    assert validated_login('Some_Channel') == 'some_channel'
    for value in ['', None, 'a\r\nPRIVMSG #x :bad', 'a b', '#channel', 'a' * 26]:
        with pytest.raises(ValueError):
            validated_login(value)


def test_chat_tls_uses_packaged_roots_instead_of_build_machine_paths(monkeypatch):
    import certifi
    context = Mock()
    context.wrap_socket.return_value.recv.return_value = b''
    create = Mock(return_value=context)
    monkeypatch.setattr('worker.chat_inputs.ssl.create_default_context',create)
    monkeypatch.setattr('worker.chat_inputs.socket.create_connection',Mock(return_value=Mock()))
    watcher = ChatWatcher({'platform':'twitch','login':'room'},Mock(),threading.Event())
    watcher._receive()
    create.assert_called_once_with(cafile=certifi.where())


def test_parser_only_delivers_requested_room_message_without_identity():
    assert parse_privmsg(':alice!alice@host PRIVMSG #room :hello: world', 'room') == 'hello: world'
    assert parse_privmsg('@id=abc :alice!alice@host PRIVMSG #room :wow', 'room') == 'wow'
    for value in [':a!a@host PRIVMSG #else :hello', ':host NOTICE #room :hello', 'PING :host', ':a!a@host PRIVMSG #room hello', ':a!a@host PRIVMSG #room :x\r\n']:
        assert parse_privmsg(value, 'room') is None


def test_message_and_line_bounds():
    assert len(parse_privmsg(':a!a@host PRIVMSG #room :' + 'x' * 1000, 'room')) == MAX_MESSAGE_CHARS
    assert parse_privmsg(':a!a@host PRIVMSG #room :' + 'x' * 9000, 'room') is None


def test_kick_unavailable_and_cancelled_twitch_do_not_connect(monkeypatch):
    connect = Mock(); monkeypatch.setattr('worker.chat_inputs.socket.create_connection', connect)
    callback = Mock(); stop = threading.Event()
    watcher = ChatWatcher({'platform':'kick', 'login':'room'}, callback, stop)
    watcher.run(); assert watcher.status == 'unavailable'
    stop.set(); ChatWatcher({'platform':'twitch','login':'room'}, callback, stop).run()
    connect.assert_not_called(); callback.assert_not_called()


def test_close_interrupts_socket():
    watcher = ChatWatcher({'platform':'twitch','login':'room'}, Mock(), threading.Event())
    connection = Mock(); watcher._socket = connection; watcher.close()
    connection.shutdown.assert_called_once(); connection.close.assert_called_once()

def test_tls_join_ping_and_fragmented_message_delivery(monkeypatch):
    stop = threading.Event(); messages = []
    watcher = ChatWatcher({'platform':'twitch','login':'room'}, messages.append, stop)
    connection = Mock()
    chunks = iter([b':guest!guest@host PRIVMSG #room :before join\r\n', b':justinfan100000000!guest@host JOIN #room\r\nPING :tmi.twitch.tv\r\n:a!a@host PRIVMSG #room :hel', b'lo\r\n', b''])
    connection.recv.side_effect = lambda _: next(chunks)
    context = Mock(); context.wrap_socket.return_value = connection
    monkeypatch.setattr('worker.chat_inputs.socket.create_connection', Mock(return_value=Mock()))
    monkeypatch.setattr('worker.chat_inputs.ssl.create_default_context', Mock(return_value=context))
    monkeypatch.setattr('worker.chat_inputs.secrets.randbelow', lambda _: 0)
    watcher._receive()
    assert messages == ['hello']
    assert watcher.status == 'connected'
    assert context.wrap_socket.call_args.kwargs == {'server_hostname': 'irc.chat.twitch.tv'}
    sent = [call.args[0] for call in connection.sendall.call_args_list]
    assert sent == [b'NICK justinfan100000000\r\nJOIN #room\r\n', b'PONG :tmi.twitch.tv\r\n']


def test_reconnect_attempts_are_bounded(monkeypatch):
    watcher = ChatWatcher({'platform':'twitch','login':'room'}, Mock(), threading.Event())
    receive = Mock(side_effect=OSError()); watcher._receive = receive
    watcher._backoff = Mock(); watcher.run()
    assert receive.call_count == 3
    assert watcher.status == 'unavailable'
    assert [c.args[0] for c in watcher._backoff.call_args_list] == [1, 2]



def test_kick_channel_identifiers_do_not_use_twitch_regex():
 watcher=ChatWatcher({'platform':'kick','login':'a-channel-with-a-long-valid-slug'},Mock(),threading.Event())
 assert watcher.login=='a-channel-with-a-long-valid-slug' and watcher.status=='unavailable'


def test_authenticated_chat_uses_only_read_connection(monkeypatch):
 watcher=ChatWatcher({'platform':'twitch','login':'room'},Mock(),threading.Event(),authentication=('owner','test-token'))
 connection=Mock();connection.recv.return_value=b'';context=Mock();context.wrap_socket.return_value=connection
 monkeypatch.setattr('worker.chat_inputs.socket.create_connection',Mock(return_value=Mock()))
 monkeypatch.setattr('worker.chat_inputs.ssl.create_default_context',Mock(return_value=context))
 watcher._receive()
 assert connection.sendall.call_args.args[0]==b'PASS oauth:test-token\r\nNICK owner\r\nJOIN #room\r\n'
