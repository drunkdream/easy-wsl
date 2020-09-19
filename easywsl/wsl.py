# -*- coding: UTF-8 -*-

"""WSL interface
"""


import asyncio
import sys

from . import utils


class StreamReader(object):
    def __init__(self, proc, name):
        self._name = name
        self._stream = getattr(proc, name)

    @property
    def name(self):
        return self._name

    async def readline(self):
        return await self._stream.readline()


class WSL(object):
    def __init__(self, root_pwd=None):
        self._root_pwd = root_pwd

    async def _run_shell_cmd(self, cmdline, root=False, write_to_stdout=False):
        if root:
            if not self._root_pwd:
                raise RuntimeError("root password not specified")
            cmdline = "echo '%s' ^| sudo -S %s" % (self._root_pwd, cmdline)
        cmdline = "C:\Windows\\system32\\wsl.exe " + cmdline
        if write_to_stdout:
            print("$ " + cmdline)
        proc = await asyncio.create_subprocess_shell(
            cmdline, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        tasks = [None, None]
        stdout = stderr = ""
        while proc.returncode is None:
            if tasks[0] is None:
                tasks[0] = asyncio.ensure_future(proc.stdout.readline())
            if tasks[1] is None:
                tasks[1] = asyncio.ensure_future(proc.stderr.readline())
            done_tasks, _ = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done_tasks:
                line = task.result().decode().replace("\x00", "")
                if task == tasks[0]:
                    if write_to_stdout:
                        sys.stdout.write(line)
                    stdout += line
                    tasks[0] = None
                else:
                    if write_to_stdout:
                        sys.stderr.write(line)
                    stderr += line
                    tasks[1] = None
        return proc.returncode, stdout, stderr

    async def run_shell_cmd(self, cmdline, root=False, write_to_stdout=False):
        return_code, stdout, stderr = await self._run_shell_cmd(
            cmdline, root, write_to_stdout
        )
        if return_code:
            raise RuntimeError(
                "Run cmdline %s failed: [%d] %s" % (cmdline, return_code, stderr)
            )
        return stdout

    async def check_iptables_rule(self, rule, table=None):
        cmdline = "iptables"
        if table:
            cmdline += " -t %s" % table
        cmdline += " -L"
        result = await self.run_shell_cmd(cmdline, True)
        if rule in result:
            return True
        return False

    async def clear_iptables(self, table=None):
        cmdline = "iptables -F"
        if table:
            cmdline += " -t %s" % table
        await self.run_shell_cmd(cmdline, True)

    async def forward_local_port(
        self, local_port, remote_port, remote_address="127.0.0.1"
    ):
        if await self.check_iptables_rule(
            "LOCAL tcp dpt:%d to:%s:%d" % (local_port, remote_address, remote_port),
            "nat",
        ):
            utils.logger.info(
                "[%s] NAT rule from localhost:%d to %s:%d exist"
                % (self.__class__.__name__, local_port, remote_address, remote_port)
            )
            return

        utils.logger.info(
            "[%s] Create iptables nat rules: %d => %d"
            % (self.__class__.__name__, local_port, remote_port)
        )
        cmdline = (
            "iptables -t nat -A OUTPUT -m addrtype --src-type LOCAL --dst-type LOCAL -p tcp --dport %d -j DNAT --to-destination %s:%d"
            % (local_port, remote_address, remote_port)
        )
        await self.run_shell_cmd(cmdline, True)
        cmdline = "iptables -t nat -A POSTROUTING -m addrtype --src-type LOCAL --dst-type UNICAST -j MASQUERADE"
        await self.run_shell_cmd(cmdline, True)
        cmdline = "cat /proc/sys/net/ipv4/conf/all/route_localnet"
        result = await self.run_shell_cmd(cmdline)
        if int(result.strip()) == 0:
            cmdline = "sysctl -w net.ipv4.conf.eth0.route_localnet=1"
            await self.run_shell_cmd(cmdline, True)
