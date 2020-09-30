# -*- coding: UTF-8 -*-

"""
"""

import asyncio
import ctypes
import json
import logging
import os
import socket
import sys
import time
import shutil
import urllib.request

import win32com.client
import win32gui


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
        raise RuntimeError("Add firewall rule needs run as administrator")
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


async def run_command(cmdline, env=None, write_to_stdout=False):
    if write_to_stdout:
        print("\n\x1b[1;33m$ %s\x1b[0;0m\n" % cmdline)

    proc = await asyncio.create_subprocess_shell(
        cmdline,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    tasks = [None, None]
    stdout = stderr = ""
    while True:
        if tasks[0] is None:
            tasks[0] = asyncio.ensure_future(proc.stdout.read(8192))
        if tasks[1] is None:
            tasks[1] = asyncio.ensure_future(proc.stderr.read(8192))
        done_tasks, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for task in done_tasks:
            result = task.result()
            for encoding in ("utf8", "gbk", "utf16"):
                try:
                    result = result.decode(encoding)
                except UnicodeDecodeError:
                    pass
                else:
                    result = result.replace('\x00', '')
                    break
            else:
                raise RuntimeError("Unknown encoding: %r" % result)

            for line in result.splitlines():
                if not line:
                    continue

                if task == tasks[0]:
                    if write_to_stdout:
                        sys.stdout.write(line + "\n")
                    stdout += line + "\n"
                else:
                    if write_to_stdout:
                        sys.stderr.write("\x1b[1;31m%s\x1b[0;0m\n" % line)
                    stderr += line + "\n"

            if task == tasks[0]:
                tasks[0] = None
            else:
                tasks[1] = None

        if proc.returncode is not None:
            break
    return proc.returncode, stdout, stderr


def run_coroutine(coro):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


def sync_run_command(cmdline, write_to_stdout=False):
    return run_coroutine(run_command(cmdline, write_to_stdout=write_to_stdout))


def download(url, save_path):
    proxies = {}
    http_proxy = os.environ.get("http_proxy")
    if http_proxy:
        proxies["http"] = http_proxy
    https_proxy = os.environ.get("https_proxy")
    if https_proxy:
        proxies["https"] = https_proxy
    if proxies:
        proxy_handler = urllib.request.ProxyHandler(proxies)
        opener = urllib.request.build_opener(proxy_handler)
        urllib.request.install_opener(opener)

    time0 = time.time()
    with open(save_path, "wb") as fp:
        with urllib.request.urlopen(url) as response:
            read_size = 0
            total_size = response.headers["Content-Length"]
            if total_size:
                total_size = int(total_size)
                sys.stdout.write("0%% 0/%d 0B/s" % total_size)
                sys.stdout.flush()

            while not total_size or read_size < total_size:
                buffer = response.read(64 * 1024)
                if not buffer:
                    break
                fp.write(buffer)
                read_size += len(buffer)
                speed = read_size / (time.time() - time0)
                unit = "B/s"
                if speed > 1024:
                    speed /= 1024
                    unit = "KB/s"
                if speed > 1024:
                    speed /= 1024
                    unit = "MB/s"
                if total_size:
                    sys.stdout.write(
                        "\r%.2f%% %d/%d %.2f%s"
                        % (
                            (read_size / total_size) * 100,
                            read_size,
                            total_size,
                            speed,
                            unit,
                        )
                    )
                else:
                    sys.stdout.write(
                        "\r%d %.2f%s"
                        % (
                            read_size,
                            speed,
                            unit,
                        )
                    )
                sys.stdout.flush()
            sys.stdout.write("\n")


def enable_ansi_code():
    result = ctypes.windll.kernel32.SetConsoleMode(
        ctypes.windll.kernel32.GetStdHandle(-11), 7
    )
    return result == 1


def get_env(env_list):
    env = {}
    for key in env_list:
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


def windows_path_2_wsl_path(path):
    """convert windows path to wsl path"""
    path = path.replace(":", "").replace("\\", "/")
    path = path[0].lower() + path[1:]
    if path.endswith("/"):
        path = path[:-1]
    return "/mnt/%s" % path


def get_github_latest_release(repo):
    url = "https://api.github.com/repos/%s/releases/latest" % repo
    proxies = {}
    https_proxy = os.environ.get("https_proxy")
    if https_proxy:
        proxies["https"] = https_proxy
    if proxies:
        proxy_handler = urllib.request.ProxyHandler(proxies)
        opener = urllib.request.build_opener(proxy_handler)
        urllib.request.install_opener(opener)

    with urllib.request.urlopen(url) as response:
        return json.loads(response.read())


def install_ttf(ttf_path):
    font_dir = os.path.join(os.environ["WINDIR"], "Fonts")
    font_path = os.path.join(font_dir, os.path.basename(ttf_path))
    if not os.path.isfile(font_path):
        shutil.copyfile(ttf_path, font_path)
    sync_run_command(
        r'reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts" /v "FontName (TrueType)" /t REG_SZ /d "%s" /f'
        % os.path.basename(ttf_path)
    )


def get_installed_fonts():
    def callback(font, tm, fonttype, names):
        names.append(font.lfFaceName)
        return True

    fontnames = []
    hdc = win32gui.GetDC(None)
    win32gui.EnumFontFamilies(hdc, None, callback, fontnames)
    win32gui.ReleaseDC(hdc, None)
    return fontnames


def reboot():
    while True:
        c = input("Reboot system now? Y/N ")
        c = c.upper()
        if c not in ("Y", "N"):
            continue
        elif c == "N":
            print("[+] You need reboot manually, and run this command again")
            return 0
        else:
            print(
                "[+] System will reboot in 10 seconds, you should run this command again after reboot"
            )
            sync_run_command("shutdown -r -t 10", True)
            return 0
