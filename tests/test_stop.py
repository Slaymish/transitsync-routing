from transitsync_routing.stop import Stop


def test_stop_repr():
    stop = Stop('123', 'My Stop', 1.0, 2.0)
    assert 'My Stop' in repr(stop)
    assert '123' in repr(stop)
