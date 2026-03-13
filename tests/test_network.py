from src.utils.network import is_local_hostname, resolve_request_proxy


def test_is_local_hostname_detects_compose_service_names():
    assert is_local_hostname("rsshub") is True
    assert is_local_hostname("postgres") is True


def test_is_local_hostname_detects_local_and_private_addresses():
    assert is_local_hostname("localhost") is True
    assert is_local_hostname("127.0.0.1") is True
    assert is_local_hostname("192.168.1.10") is True
    assert is_local_hostname("host.docker.internal") is True


def test_is_local_hostname_does_not_mark_public_domain_as_local():
    assert is_local_hostname("news.google.com") is False


def test_resolve_request_proxy_bypasses_local_urls():
    proxy = "http://proxy.internal:7890"

    assert resolve_request_proxy("http://rsshub:1200/telegram/channel/foo", proxy) is None
    assert resolve_request_proxy("http://localhost:1200/telegram/channel/foo", proxy) is None


def test_resolve_request_proxy_keeps_proxy_for_external_urls():
    proxy = "http://proxy.internal:7890"

    assert (
        resolve_request_proxy(
            "https://news.google.com/rss/search?q=test",
            proxy,
        )
        == proxy
    )
