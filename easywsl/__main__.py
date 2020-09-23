# -*- coding: UTF-8 -*-

"""main
"""

import argparse
import asyncio
import base64
import ctypes
import logging
import os
import platform
import sys
import tempfile
import time
import shutil
import urllib.parse
import zipfile
from xml.dom import minidom

from . import forward
from . import utils
from . import wsl

ERROR_SUCCESS_REBOOT_REQUIRED = 3010


WSL_IMAGES = {
    "amd64": {
        "Ubuntu-20.04": "https://aka.ms/wslubuntu2004",
        "Ubuntu-18.04": "https://aka.ms/wsl-ubuntu-1804",
        "Ubuntu-16.04": "https://aka.ms/wsl-ubuntu-1604",
        "Debian": "https://aka.ms/wsl-debian-gnulinux",
        "Kali-Linux": "https://aka.ms/wsl-kali-linux-new",
        "OpenSUSE-42": "https://aka.ms/wsl-opensuse-42",
        "SLES-12": "https://aka.ms/wsl-sles-12",
        "FedoraRemix": "https://github.com/WhitewaterFoundry/Fedora-Remix-for-WSL/releases/download/31.5.0/Fedora-Remix-for-WSL_31.5.0.0_x64_arm64.appxbundle",
    }
}


def system(cmdline, workdir=None):
    current_workdir = None
    if workdir:
        current_workdir = os.getcwd()
        os.chdir(workdir)
    result = os.system(cmdline)
    if workdir:
        os.chdir(current_workdir)
    return result


def show_wsl_info(args):
    sysinfo = utils.get_system_info()
    print(
        "%s \x1b[1;33m%s\x1b[0;0m Version \x1b[1;36m%s\x1b[0;0m"
        % (sysinfo["Name"], sysinfo["Release"], sysinfo["Version"])
    )
    if not wsl.WSL.check():
        print("WSL not enabled")
        return

    wsl_list = utils.run_coroutine(utils.get_wsl_list())
    print("\x1b[1;90mLinux distribution installed:\x1b[0;0m")
    for it in wsl_list:
        print(
            "%s\x1b[1;92m%s\x1b[0;0m\t"
            % (" \x1b[1;31m=>\x1b[0;0m " if it["default"] else "    ", it["name"])
        )


def enable_wsl():
    print("[+] Enabling WSL")
    returncode, _, _ = utils.sync_run_command(
        "dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart",
        True,
    )

    if returncode != ERROR_SUCCESS_REBOOT_REQUIRED:
        print("[-] Enable WSL failed", file=sys.stderr)
        return -1

    print("[+] Enable WSL success, system needs reboot")
    while True:
        c = input("Reboot system now? Y/N ")
        if c not in ("Y", "N"):
            continue
        elif c == "N":
            print("[+] You need reboot manually, and run this command again")
            return 0
        else:
            print(
                "[+] System will reboot in 10 seconds, you should run this command again after reboot"
            )
            utils.sync_run_command("shutdown -r -t 10", True)
            return 0


def install_linux(name, install_path):
    image_url = WSL_IMAGES[platform.machine().lower()].get(name)
    if not image_url:
        raise RuntimeError("Linux image %s not found" % name)
    print("[+] Downloading %s image %s" % (name, image_url))
    save_path = tempfile.mkstemp(".img")[1]
    utils.download(image_url, save_path)
    print("[+] Image file saved to %s" % save_path)
    install_path = os.path.join(install_path, name.replace(" ", "_"))
    if not os.path.isdir(install_path):
        os.makedirs(install_path)
    zf = zipfile.ZipFile(save_path, "r")
    for fname in zf.namelist():
        print("[+] Extract %s" % (fname))
        zf.extract(fname, install_path)
    zf.close()

    manifest_file = os.path.join(install_path, "AppxManifest.xml")
    if not os.path.isfile(manifest_file):
        raise RuntimeError("Invalid WSL path: %s" % install_path)
    dom = minidom.parse(manifest_file)
    app_node = dom.getElementsByTagName("Application")[0]
    install_exe = app_node.getAttribute("Executable")
    if not install_exe:
        raise RuntimeError("Invalid AppxManifest.xml in %s" % install_path)
    install_exe = os.path.join(install_path, install_exe)
    if not os.path.isfile(install_exe):
        for it in os.listdir(install_path):
            if not it.endswith(".appx"):
                continue
            path = os.path.join(install_path, it)
            if not os.path.isfile(path):
                continue
            zf = zipfile.ZipFile(path, "r")
            for fname in zf.namelist():
                print("[+] Extract %s from %s" % (fname, it))
                zf.extract(fname, install_path)
            zf.close()
        if not os.path.isfile(install_exe):
            raise RuntimeError("Install exe %s not found" % install_exe)

    if os.path.dirname(install_exe) != install_path:
        # copy install file to install path
        shutil.copy(install_exe, install_path)
        install_exe = os.path.join(install_path, os.path.basename(install_exe))

    print("[+] Run command %s" % install_exe)
    system(install_exe, install_path)
    try:
        os.remove(save_path)
    except PermissionError:
        print("[-] Remove temp file %s failed, pls delete it manually" % save_path)


def uninstall_wsl(args):
    wsl_list = utils.run_coroutine(utils.get_wsl_list())
    wsl_list = [it["name"].lower() for it in wsl_list]
    if args.distribution.lower() not in wsl_list:
        raise RuntimeError("Linux %s not installed" % args.distribution)
    print("[+] Uninstalling %s" % args.distribution)
    cmdline = 'wslconfig /u "%s"' % args.distribution
    os.system(cmdline)
    print("[+] Uninstall %s completed" % args.distribution)


def install_wsl(args):
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError("Install WSL needs run as administrator")
    if not wsl.WSL.check():
        return enable_wsl()
    else:
        install_path = args.install_path or r"C:\Linux"
        install_linux(args.distribution, install_path)


def set_default_distribution(args):
    wsl_list = utils.run_coroutine(utils.get_wsl_list())
    wsl_list = [it["name"].lower() for it in wsl_list]
    if args.distribution.lower() not in wsl_list:
        raise RuntimeError("Linux %s not installed" % args.distribution)
    print("[+] Set default distribution as %s" % args.distribution)
    cmdline = 'wslconfig /s "%s"' % args.distribution
    os.system(cmdline)
    print("[+] Set default distribution as %s completed" % args.distribution)


def forward_ports(args):
    ports = [int(port) for port in args.ports.split(";")]
    password = args.password
    wsl_addr = utils.get_wsl_adapter_address()
    utils.logger.info("WSL interface address is %s" % wsl_addr)
    o_wsl = wsl.WSL(password)
    for port in ports:
        if not utils.is_port_listening(port, wsl_addr):
            # Listen on wsl address
            utils.logger.info(
                "Forwarding localhost port %d to %s:%d" % (port, wsl_addr, port)
            )
            forwarder = forward.PortForwarder(wsl_addr, port)
            forwarder.start()
        utils.ensure_add_firewall_rule(port)
        utils.safe_ensure_future(o_wsl.forward_local_port(port, port, wsl_addr))
    utils.logger.info("Start forwarding service")
    asyncio.get_event_loop().run_forever()


def install_zsh(args):
    wsl_list = utils.run_coroutine(utils.get_wsl_list())
    wsl_list = [it["name"].lower() for it in wsl_list]
    if args.distribution and args.distribution.lower() not in wsl_list:
        raise RuntimeError("Linux %s not installed" % args.distribution)

    theme = args.theme or "agnoster"
    owsl = wsl.WSL(args.password, args.distribution)
    cmdline = """
$(which apt || which yum) update
$(which apt || which yum) install -y git
$(which apt || which yum) install -y zsh
"""
    env = utils.get_env(["http_proxy", "https_proxy"])
    utils.run_coroutine(owsl.run_shell_cmd(cmdline, True, env, True))
    cmdline = (
        """
if [ ! -d ~/.oh-my-zsh ]; then
    wget https://raw.github.com/robbyrussell/oh-my-zsh/master/tools/install.sh -O - | sh
fi
ls -l ~/.oh-my-zsh/templates/zshrc.zsh-template
cp -p ~/.oh-my-zsh/templates/zshrc.zsh-template ~/.zshrc
cat ~/.zshrc | sed s/robbyrussell/%s/g > ~/.zshrc1
mv ~/.zshrc1 ~/.zshrc
cat ~/.zshrc
"""
        % theme
    )
    utils.run_coroutine(owsl.run_shell_cmd(cmdline, False, env, True))
    font_url = "https://raw.githubusercontent.com/powerline/fonts/master/NotoMono/Noto%20Mono%20for%20Powerline.ttf"
    save_path = os.path.join(
        tempfile.mkdtemp(), urllib.parse.unquote(font_url.split("/")[-1])
    )
    utils.download(font_url, save_path)
    utils.install_ttf(save_path)

    if args.set_default_shell:
        cmdline = "echo %s ^| chsh -s /bin/zsh" % args.password
        utils.run_coroutine(owsl.run_shell_cmd(cmdline))


def install_wsl_terminal(wsl, env, install_path, default_shell):
    cmdline = """
$(which apt || which yum) update
$(which apt || which yum) install -y p7zip-full
"""
    cmdline = """bash -c "$(echo -e '%s')" """ % cmdline.replace(
        "\\", "\\\\"
    ).replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n")

    utils.run_coroutine(wsl.run_shell_cmd(cmdline, True, env, True))
    wsl_install_path = utils.windows_path_2_wsl_path(install_path)
    cmdline = (
        'cd %s;bash -c "$(wget https://raw.githubusercontent.com/mskyaxl/wsl-terminal/master/scripts/install.sh -qO -)"'
        % wsl_install_path
    )
    utils.run_coroutine(wsl.run_shell_cmd(cmdline, env=env, write_to_stdout=True))
    cmdline = (
        r'cd /d "%(install_path)s\tools" && cscript /nologo "1-add-open-wsl-terminal-here-menu.js"'
        % {"install_path": os.path.join(install_path, "wsl-terminal")}
    )
    utils.sync_run_command(cmdline, write_to_stdout=True)
    with open(
        os.path.join(install_path, "wsl-terminal", "etc", "minttyrc"), 'w'
    ) as fp:
        fp.write(
            """Emojis=openmoji
ThemeFile=base16-solarized-dark.minttyrc
Font=Noto Mono for Powerline
FontHeight=12"""
        )
    terminal_conf = os.path.join(install_path, "wsl-terminal", "etc", "wsl-terminal.conf")
    with open(terminal_conf) as fp:
        text = fp.read()
    conf_text = ''
    for line in text.splitlines():
        if not line or line[0] == ';':
            conf_text += line + '\n'
            continue
        if line.startswith('shell='):
            line = line[:6] + default_shell
        conf_text += line + '\n'
    with open(terminal_conf, 'w') as fp:
        fp.write(conf_text)
    print("Install wsl-terminal success")


def install_terminal(args):
    args.install_path = os.path.abspath(args.install_path)
    if not os.path.isdir(args.install_path):
        raise RuntimeError("Install path %s not found" % args.install_path)
    owsl = wsl.WSL(args.password)
    env = utils.get_env(["http_proxy", "https_proxy"])
    if args.name == "wsl-terminal":
        install_wsl_terminal(owsl, env, args.install_path, args.default_shell)
    elif args.name == "windows-terminal":
        sysinfo = utils.get_system_info()
        if sysinfo["Release"] < "1903":
            raise RuntimeError("Windows Terminal only support 1903 and later")
        latest_release = utils.get_github_latest_release("microsoft/terminal")
        for it in latest_release["assets"]:
            if not it["name"].endswith(".msixbundle"):
                continue
            url = it["browser_download_url"]
            save_path = tempfile.mkstemp(".msixbundle")[1]
            utils.download(url, save_path)
            cmdline = 'powershell Add-AppxPackage "%s"' % save_path
            utils.sync_run_command(cmdline, write_to_stdout=True)
    else:
        raise NotImplementedError(args.name)


def main():
    utils.enable_ansi_code()
    loop = asyncio.ProactorEventLoop()
    asyncio.set_event_loop(loop)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s][%(levelname)s]%(message)s")
    handler.setFormatter(formatter)
    utils.logger.setLevel(logging.DEBUG)
    utils.logger.propagate = 0
    utils.logger.addHandler(handler)

    parser = argparse.ArgumentParser(
        prog="ezwsl", description="Easy deploy wsl cmdline tool."
    )

    subparsers = parser.add_subparsers(dest="Sub command")
    parser_info = subparsers.add_parser("ls")
    parser_info.set_defaults(func=show_wsl_info)

    parser_install = subparsers.add_parser("install")
    parser_install.add_argument(
        "-d",
        "--distribution",
        help="linux distribution name",
        choices=WSL_IMAGES[platform.machine().lower()].keys(),
        required=True,
    )
    parser_install.add_argument("--install-path", help="path of linux to install")
    parser_install.set_defaults(func=install_wsl)

    parser_uninstall = subparsers.add_parser("uninstall")
    parser_uninstall.add_argument(
        "-d",
        "--distribution",
        help="linux distribution name",
        required=True,
    )
    parser_uninstall.set_defaults(func=uninstall_wsl)

    parser_setdefault = subparsers.add_parser("setdefault")
    parser_setdefault.add_argument(
        "-d",
        "--distribution",
        help="linux distribution name",
        required=True,
    )
    parser_setdefault.set_defaults(func=set_default_distribution)

    parser_install_zsh = subparsers.add_parser("install-zsh")
    parser_install_zsh.add_argument(
        "-p", "--password", help="current user password", required=True
    )
    parser_install_zsh.add_argument(
        "-d",
        "--distribution",
        help="linux distribution name, default is current distribution",
    )
    parser_install_zsh.add_argument(
        "--theme", help="zsh theme to use, default is agnoster", default="agnoster"
    )
    parser_install_zsh.add_argument(
        "--set-default-shell",
        help="is set zsh as default shell",
        default=False,
        action="store_true",
    )
    parser_install_zsh.set_defaults(func=install_zsh)

    parser_install_terminal = subparsers.add_parser("install-terminal")
    parser_install_terminal.add_argument(
        "-n",
        "--name",
        help="terminal name",
        choices=["wsl-terminal", "windows-terminal"],
        required=True,
    )
    parser_install_terminal.add_argument(
        "-p", "--password", help="current user password"
    )
    parser_install_terminal.add_argument(
        "--install-path", help="the path to install terminal", default="D:\\"
    )
    parser_install_terminal.add_argument(
        "--default-shell", help="default terminal shell", default="/bin/bash"
    )
    parser_install_terminal.set_defaults(func=install_terminal)

    parser_forward = subparsers.add_parser("forward")
    parser_forward.add_argument(
        "--ports",
        help="port list forward from windows to wsl2(separated by ;)",
        required=True,
    )
    parser_forward.add_argument(
        "-p", "--password", help="current user password", required=True
    )
    parser_forward.set_defaults(func=forward_ports)

    args = sys.argv[1:]
    if not args:
        parser.print_help()
        return 0

    args = parser.parse_args(args)
    args.func(args)


if __name__ == "__main__":
    if sys.platform != "win32":
        print("This script can only run on windows", file=sys.stderr)
    else:
        sys.exit(main())
