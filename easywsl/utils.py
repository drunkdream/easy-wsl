# -*- coding: UTF-8 -*-

"""
"""

import asyncio
import ctypes
import logging
import os
import socket
import sys

import win32com.client


logger = logging.getLogger("easywsl")


version_map = {
    "19041": "2004",
    "18363": "1909",
    "18362": "1903",
    "17763": "1809",
    "17134": "1803",
}


def get_windows_release(build_num):
    if build_num in version_map:
        return version_map[build_num]
    return None


def get_system_info():
    result = {}
    wmi = win32com.client.GetObject("winmgmts:")
    for it in wmi.InstancesOf("Win32_OperatingSystem"):
        result["Name"] = it.Caption
        result["Version"] = it.Version
        result["Release"] = get_windows_release(it.BuildNumber)
    return result


def get_wsl_adapter_address():
    wmi = win32com.client.GetObject("winmgmts:")
    for interface in wmi.InstancesOf("Win32_NetworkAdapterConfiguration"):
        if not interface.IPEnabled:
            continue

        if interface.Description == "Hyper-V Virtual Ethernet Adapter":
            return interface.IPAddress[0]
    return None


async def is_port_allowed_by_firewall(port):
    _, stdout, _ = await run_command(
        'netsh advfirewall firewall show rule dir=in status=enabled name="EasyWSL %d"'
        % port
    )
    for line in stdout.splitlines():
        if str(port) in line:
            return True
    return False


async def add_firewall_rule(port):
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError("Add firewall rule needs run as admin")
    await run_command(
        'netsh advfirewall firewall add rule name= "EasyWSL %d" dir=in action=allow protocol=TCP localport=%d'
        % (port, port)
    )


def ensure_add_firewall_rule(port):
    if not run_coroutine(is_port_allowed_by_firewall(port)):
        run_coroutine(add_firewall_rule(port))


def is_port_listening(port, addr="127.0.0.1"):
    try:
        s = socket.socket()
        s.bind((addr, port))
    except:
        return True
    else:
        s.close()
        return False


def safe_ensure_future(coro):
    async def _wrap_func():
        try:
            return await coro
        except:
            logger.exception("Run coroutine %s failed" % coro.__name__)

    asyncio.ensure_future(_wrap_func())


async def run_command(cmdline, write_to_stdout=False):
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
        done_tasks, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done_tasks:
            line = task.result()
            try:
                line = line.decode("utf8")
            except UnicodeDecodeError:
                line = line.decode("gbk")
            line = line.replace("\x00", "")
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


def run_coroutine(coro):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)
