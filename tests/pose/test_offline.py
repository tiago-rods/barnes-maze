"""A proteção usa apenas sockets Python locais; estes testes não acessam a rede."""

import os
import socket
from unittest.mock import Mock

import pytest

from barnes.pose.offline import OfflineNetworkError, offline_network


@pytest.mark.parametrize("host", ["example.org", "192.0.2.1", "2001:db8::1", "0.0.0.0"])
@pytest.mark.parametrize("operation", ["connect", "connect_ex"])
def test_external_connections_are_refused_before_the_underlying_call(monkeypatch, host, operation):
    original = Mock()
    monkeypatch.setattr(socket.socket, operation, original)
    with (
        socket.socket() as connection,
        offline_network(),
        pytest.raises(OfflineNetworkError, match="bloqueado"),
    ):
        getattr(connection, operation)((host, 443))
    original.assert_not_called()


@pytest.mark.parametrize(
    "operation,argument",
    [
        ("getaddrinfo", "example.org"),
        ("gethostbyname", "example.org"),
        ("gethostbyname_ex", "example.org"),
        ("gethostbyaddr", "192.0.2.1"),
        ("getnameinfo", ("192.0.2.1", 80)),
        ("create_connection", ("example.org", 443)),
    ],
)
def test_dns_and_create_connection_refuse_remote_hosts(monkeypatch, operation, argument):
    original = Mock()
    monkeypatch.setattr(socket, operation, original)
    with offline_network(), pytest.raises(OfflineNetworkError):
        getattr(socket, operation)(argument)
    original.assert_not_called()


@pytest.mark.parametrize("flags", [(), (0,)])
def test_external_udp_is_refused(monkeypatch, flags):
    original = Mock()
    monkeypatch.setattr(socket.socket, "sendto", original)
    with (
        socket.socket(type=socket.SOCK_DGRAM) as connection,
        offline_network(),
        pytest.raises(OfflineNetworkError),
    ):
        connection.sendto(b"test", *flags, ("192.0.2.1", 53))
    original.assert_not_called()


@pytest.mark.parametrize("operation", ["send", "sendall"])
def test_connection_opened_before_context_cannot_send_remotely(monkeypatch, operation):
    original = Mock()
    monkeypatch.setattr(socket.socket, operation, original)
    monkeypatch.setattr(socket.socket, "getpeername", lambda self: ("192.0.2.1", 443))
    with socket.socket() as connection, offline_network(), pytest.raises(OfflineNetworkError):
        getattr(connection, operation)(b"test")
    original.assert_not_called()


def test_real_loopback_tcp_still_works():
    with offline_network(), socket.socket() as server:
        server.settimeout(2)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.create_connection(server.getsockname(), timeout=2) as client:
            accepted, _ = server.accept()
            with accepted:
                accepted.settimeout(2)
                client.sendall(b"local only")
                assert accepted.recv(32) == b"local only"
                accepted.send(b"ok")
                assert client.recv(32) == b"ok"


def test_real_loopback_udp_still_works():
    with offline_network(), socket.socket(type=socket.SOCK_DGRAM) as server:
        server.settimeout(2)
        server.bind(("127.0.0.1", 0))
        with socket.socket(type=socket.SOCK_DGRAM) as client:
            client.sendto(b"local", 0, server.getsockname())
            data, address = server.recvfrom(32)
            assert data == b"local"
            assert address[0] == "127.0.0.1"


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "::ffff:127.0.0.1"])
def test_numeric_loopback_addresses_allowed_without_external_dns(monkeypatch, host):
    original = Mock(return_value=[])
    monkeypatch.setattr(socket, "getaddrinfo", original)
    with offline_network():
        assert socket.getaddrinfo(host, 0) == []
    original.assert_called_once_with(host, 0)


def test_ipv6_connect_accepts_four_part_address(monkeypatch):
    original = Mock(return_value=0)
    monkeypatch.setattr(socket.socket, "connect_ex", original)
    if not socket.has_ipv6:
        pytest.skip("IPv6 indisponível nesta máquina")
    with socket.socket(socket.AF_INET6) as connection, offline_network():
        assert connection.connect_ex(("::1", 1234, 0, 0)) == 0
    original.assert_called_once()


@pytest.mark.parametrize("host", ["localhost", "LOCALHOST", "localhost.", b"localhost", None])
def test_local_host_lookup_and_passive_lookup_allowed(monkeypatch, host):
    original = Mock(return_value=[])
    monkeypatch.setattr(socket, "getaddrinfo", original)
    with offline_network():
        socket.getaddrinfo(host, 1234)
    original.assert_called_once_with(host, 1234)


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="AF_UNIX indisponível")
def test_unix_socket_path_allowed(monkeypatch):
    original = Mock(return_value=None)
    monkeypatch.setattr(socket.socket, "connect", original)
    try:
        connection = socket.socket(socket.AF_UNIX)
    except OSError:
        pytest.skip("Sistema não suporta AF_UNIX")
    with connection, offline_network():
        connection.connect("worker.sock")
    original.assert_called_once()


def _hooks():
    return {
        name: getattr(socket, name)
        for name in (
            "getaddrinfo",
            "getnameinfo",
            "gethostbyname",
            "gethostbyname_ex",
            "gethostbyaddr",
            "create_connection",
        )
    } | {
        f"socket.{name}": getattr(socket.socket, name)
        for name in ("connect", "connect_ex", "send", "sendall", "sendto")
    }


@pytest.mark.parametrize("raise_inside", [False, True])
def test_hooks_and_environment_restored_on_all_exit_paths(monkeypatch, raise_inside):
    monkeypatch.setenv("WANDB_MODE", "original-mode")
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    previous_env = dict(os.environ)
    original_hooks = _hooks()
    try:
        with offline_network():
            assert os.environ["WANDB_DISABLED"] == "true"
            assert os.environ["WANDB_MODE"] == "disabled"
            for name in (
                "HF_HUB_OFFLINE",
                "HF_HUB_DISABLE_TELEMETRY",
                "TRANSFORMERS_OFFLINE",
                "DO_NOT_TRACK",
            ):
                assert os.environ[name] == "1"
            assert socket.socket.connect is not original_hooks["socket.connect"]
            if raise_inside:
                raise RuntimeError("worker failed")
    except RuntimeError:
        assert raise_inside
    assert dict(os.environ) == previous_env
    assert _hooks() == original_hooks


def test_nested_context_restores_outer_guard_then_original_state():
    original_hooks = _hooks()
    previous_env = dict(os.environ)
    with offline_network():
        outer_hooks = _hooks()
        with offline_network(), pytest.raises(OfflineNetworkError):
            socket.gethostbyname("example.org")
        assert _hooks() == outer_hooks
        assert os.environ["HF_HUB_OFFLINE"] == "1"
        with pytest.raises(OfflineNetworkError):
            socket.create_connection(("192.0.2.1", 443))
    assert _hooks() == original_hooks
    assert dict(os.environ) == previous_env
