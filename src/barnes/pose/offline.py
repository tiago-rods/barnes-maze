"""Proteção offline para workers Python de treino/inferência (US-07/US-08).

O contexto bloqueia conexões/DNS externos através da API Python de ``socket``
e desativa integrações comuns de telemetria e download. Loopback IPv4/IPv6
e sockets locais AF_UNIX continuam disponíveis para coordenação de workers.

É uma proteção do processo Python, não um firewall, sandbox de segurança ou
prova de desconexão física da máquina. Bibliotecas nativas podem ignorar a API
Python e processos novos não herdam seus hooks. Cada worker deve entrar neste
contexto; a validação final US-08 ainda exige executar na máquina do laboratório
efetivamente sem rede. Nenhuma configuração de rede do sistema é alterada.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import wraps

_CONTEXT_LOCK = threading.RLock()
_OFFLINE_ENV = {
    "WANDB_DISABLED": "true",
    "WANDB_MODE": "disabled",
    "HF_HUB_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "DO_NOT_TRACK": "1",
}


class OfflineNetworkError(PermissionError):
    """Tentativa de acessar um endereço externo durante execução offline."""


def _require_loopback(host: object) -> None:
    """Valida o host sem fazer resolução DNS para decidir se ele é local."""
    if isinstance(host, bytes):
        try:
            host = host.decode("ascii")
        except UnicodeDecodeError:
            host = None
    if isinstance(host, str):
        if host.lower().rstrip(".") == "localhost":
            return
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            if address.is_loopback:
                return
            if isinstance(address, ipaddress.IPv6Address):
                mapped = address.ipv4_mapped
                if mapped is not None and mapped.is_loopback:
                    return
    raise OfflineNetworkError(f"Execução offline: acesso externo bloqueado ({host!r}).")


def _require_local_socket(sock: socket.socket, address: object = None) -> None:
    unix_family = getattr(socket, "AF_UNIX", None)
    if unix_family is not None and sock.family == unix_family:
        return
    if sock.family not in (socket.AF_INET, socket.AF_INET6):
        raise OfflineNetworkError(f"Execução offline: família de socket bloqueada ({sock.family}).")
    if address is None:
        try:
            address = sock.getpeername()
        except OSError as exc:
            raise OfflineNetworkError(
                "Execução offline: socket sem destino local confirmado."
            ) from exc
    if not isinstance(address, tuple) or len(address) < 2:
        raise OfflineNetworkError("Execução offline: endereço de socket inválido.")
    _require_loopback(address[0])


@contextmanager
def offline_network() -> Iterator[None]:
    """Permite apenas comunicação local pela API Python enquanto o contexto durar.

    Restaura os hooks e as variáveis anteriores em saída normal ou por exceção,
    inclusive com contextos aninhados. Os hooks afetam todas as threads deste
    processo. Um lock serializa contextos abertos por threads diferentes;
    portanto não envolva outra thread que precise entrar no contexto e aguarde
    sua conclusão dentro de um contexto já aberto.

    Exemplos:
        >>> with offline_network():
        ...     # Importar backend, carregar pesos locais e executar aqui.
        ...     pass

    Raises:
        OfflineNetworkError: A operação tenta alcançar um destino off-machine.
    """
    with _CONTEXT_LOCK:
        patches: list[tuple[object, str, object]] = []
        previous_env = {key: os.environ.get(key) for key in _OFFLINE_ENV}

        def patch(target, name, replacement):
            patches.append((target, name, getattr(target, name)))
            setattr(target, name, replacement)

        def address_operation(original):
            @wraps(original)
            def guarded(sock, address, *args, **kwargs):
                _require_local_socket(sock, address)
                return original(sock, address, *args, **kwargs)

            return guarded

        def connected_operation(original):
            @wraps(original)
            def guarded(sock, *args, **kwargs):
                _require_local_socket(sock)
                return original(sock, *args, **kwargs)

            return guarded

        def host_operation(original):
            @wraps(original)
            def guarded(host, *args, **kwargs):
                _require_loopback(host)
                return original(host, *args, **kwargs)

            return guarded

        original_getaddrinfo = socket.getaddrinfo
        original_getnameinfo = socket.getnameinfo
        original_create_connection = socket.create_connection
        original_sendto = socket.socket.sendto

        @wraps(original_getaddrinfo)
        def guarded_getaddrinfo(host, *args, **kwargs):
            # None é usado para bind/passive lookup e não consulta nome remoto.
            if host is not None:
                _require_loopback(host)
            return original_getaddrinfo(host, *args, **kwargs)

        @wraps(original_getnameinfo)
        def guarded_getnameinfo(address, *args, **kwargs):
            if not isinstance(address, tuple) or len(address) < 2:
                raise OfflineNetworkError("Execução offline: endereço DNS inválido.")
            _require_loopback(address[0])
            return original_getnameinfo(address, *args, **kwargs)

        @wraps(original_create_connection)
        def guarded_create_connection(address, *args, **kwargs):
            if not isinstance(address, tuple) or len(address) < 2:
                raise OfflineNetworkError("Execução offline: destino de conexão inválido.")
            _require_loopback(address[0])
            return original_create_connection(address, *args, **kwargs)

        @wraps(original_sendto)
        def guarded_sendto(sock, data, *args, **kwargs):
            # sendto(data, address) ou sendto(data, flags, address).
            address = kwargs.get("address", args[-1] if args else None)
            _require_local_socket(sock, address)
            return original_sendto(sock, data, *args, **kwargs)

        try:
            for name in ("connect", "connect_ex"):
                patch(socket.socket, name, address_operation(getattr(socket.socket, name)))
            # Impede também o uso de conexões externas abertas antes do contexto.
            for name in ("send", "sendall"):
                patch(socket.socket, name, connected_operation(getattr(socket.socket, name)))
            patch(socket.socket, "sendto", guarded_sendto)
            if hasattr(socket.socket, "sendmsg"):
                original_sendmsg = socket.socket.sendmsg

                @wraps(original_sendmsg)
                def guarded_sendmsg(sock, buffers, *args, **kwargs):
                    address = kwargs.get("address", args[2] if len(args) > 2 else None)
                    _require_local_socket(sock, address)
                    return original_sendmsg(sock, buffers, *args, **kwargs)

                patch(socket.socket, "sendmsg", guarded_sendmsg)
            patch(socket, "getaddrinfo", guarded_getaddrinfo)
            patch(socket, "getnameinfo", guarded_getnameinfo)
            for name in ("gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
                patch(socket, name, host_operation(getattr(socket, name)))
            patch(socket, "create_connection", guarded_create_connection)
            os.environ.update(_OFFLINE_ENV)
            yield
        finally:
            for target, name, original in reversed(patches):
                setattr(target, name, original)
            for key, previous in previous_env.items():
                if previous is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = previous
