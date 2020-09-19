# -*- coding: UTF-8 -*-

"""main
"""

import argparse
import asyncio
import logging
import sys

from . import forward
from . import utils
from . import wsl


def show_wsl_info(args):
    sysinfo = utils.get_system_info()
    print(
        "%s %s Version %s" % (sysinfo["Name"], sysinfo["Release"], sysinfo["Version"])
    )
    o_wsl = wsl.WSL()
    result = utils.run_coroutine(o_wsl.run_shell_cmd("-l -v")).strip()
    lines = result.split("\r\n")
    for line in lines[1:]:
        items = line.split()
        if items[0] == "*":
            print("Current Linux Subsystem\t%s(WSL %s)" % (items[1], items[3]))
            break


def forward_ports(args):
    ports = [int(port) for port in args.ports.split(";")]
    root_password = args.root_password
    wsl_addr = utils.get_wsl_adapter_address()
    utils.logger.info("WSL interface address is %s" % wsl_addr)
    o_wsl = wsl.WSL(root_password)
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


def main():
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
    parser_info = subparsers.add_parser("info")
    parser_info.set_defaults(func=show_wsl_info)
    parser_forward = subparsers.add_parser("forward")
    parser_forward.set_defaults(func=forward_ports)
    parser_forward.add_argument(
        "--ports",
        help="port list forward from windows to wsl2(separated by ;)",
        required=True,
    )
    parser_forward.add_argument(
        "--root-password", help="root user password", required=True
    )

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
