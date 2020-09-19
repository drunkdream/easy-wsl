# -*- coding: UTF-8 -*-

"""Forward ports from windows to wsl

"""

import asyncio

from . import utils


class PortForwarder(object):
    def __init__(self, address, port):
        self._address = address
        self._port = port

    async def handle_connection(self, reader, writer):
        up_reader, up_writer = await asyncio.open_connection("127.0.0.1", self._port)
        tasks = [None, None]
        while True:
            if tasks[0] is None:
                tasks[0] = asyncio.ensure_future(reader.read(4096))
            if tasks[1] is None:
                tasks[1] = asyncio.ensure_future(up_reader.read(4096))
            done_tasks, _ = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            assert len(done_tasks) > 0
            for task in done_tasks:
                buffer = task.result()
                print(buffer)
                if not buffer:
                    writer.close()
                    up_writer.close()
                    return
                if task == tasks[0]:
                    up_writer.write(buffer)
                    tasks[0] = None
                else:
                    writer.write(buffer)
                    tasks[1] = None

    def start(self):
        coro = asyncio.start_server(self.handle_connection, self._address, self._port)
        utils.safe_ensure_future(coro)
