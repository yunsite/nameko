import eventlet

from nameko.exceptions import WaiterTimeout


_conndrainers = {}


def _has_waiters(greenthread):
    return bool(greenthread._exit_event._waiters)


def consumefrom(conn, killdrainer=False):
    # TODO: killdrainers is never used by any caller
    id_ = id(conn)
    gt = _conndrainers.get(id_)
    if gt is None or gt.dead:
        gt = _conndrainers[id_] = eventlet.spawn(conn.drain_events)
    try:
        return gt.wait()
    finally:
        if not _has_waiters(gt):
            _conndrainers.pop(id_, None)
            if killdrainer and not gt.dead:
                gt.kill()


def queue_iterator(queue, channel=None, no_ack=False, timeout=None):
    # TODO: this is never called with channel
    if queue.is_bound:
        if channel is not None:
            raise TypeError('channel specified when queue is bound')
        channel = queue.channel
    elif channel is not None:
        queue.bind(channel)
    else:
        raise TypeError('channel can not be None for unbound queue')
    channel = queue.channel
    buf = []

    def callback(message):
        try:
            message = channel.message_to_python(message)
        except AttributeError:
            # TODO: No tests come here, so when would this happen?
            #        And, why can we just ignore it?
            pass
        buf.append(message)

    tag = queue.consume(callback=callback, no_ack=no_ack)
    with eventlet.Timeout(timeout, exception=WaiterTimeout()):
        try:
            while True:
                if buf:
                    yield buf.pop(0)
                consumefrom(channel.connection.client)
        finally:
            queue.cancel(tag)
