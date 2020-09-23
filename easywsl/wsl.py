# -*- coding: UTF-8 -*-

"""WSL interface
"""


import asyncio
import os
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
    wsl_path = "C:\Windows\\system32\\wsl.exe"

    def __init__(self, password=None, distribution=None):
        self._password = password
        self._distribution = distribution

    @staticmethod
    def check():
        return os.path.exists(WSL.wsl_path)

    async def _run_shell_cmd(
        self, cmdline, root=False, env=None, write_to_stdout=False
    ):
        if root:
            if not self._password:
                raise RuntimeError("Password not specified")
            env_params = ""
            if env:
                env_params = "-E"
            cmdline = "echo '%s' ^| sudo -S %s %s" % (
                self._password,
                env_params,
                cmdline,
            )

        wsl_params = " "
        if self._distribution:
            wsl_params += " -d %s " % self._distribution
        cmdline = self.__class__.wsl_path + wsl_params + cmdline
        if env:
            env["WSLENV"] = ":".join(env.keys())
        return await utils.run_command(cmdline, env, write_to_stdout)

    async def run_shell_cmd(self, cmdline, root=False, env=None, write_to_stdout=False):
        if "\n" in cmdline:
            cmdline = """sh -c 'echo "%s" ^| sh' """ % cmdline.replace(
                "\\", "\\\\"
            ).replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n")
        return_code, stdout, stderr = await self._run_shell_cmd(
            cmdline, root, env, write_to_stdout
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
