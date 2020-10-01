# EasyWSL

让部署WSL更轻松！

## 使用环境

操作系统：`Windows 10 1803`以上版本

Python版本：>= 3.5

> 注意：该工具只能运行在Windows系统上，不支持在WSL中运行！

## 使用帮助

### 查看已安装的WSL系统列表

```bat
> ezwsl ls
Microsoft Windows 10 专业版 2004 Version 10.0.19041
WSL distribution installed:
 => Ubuntu-20.04(WSL2)
```

### 安装WSL发行版

```bat
> ezwsl install -d Ubuntu-20.04
```

目前只能安装官方支持的几款发行版：`Ubuntu-20.04`,`Ubuntu-18.04`,`Ubuntu-16.04`,`Debian`,`Kali-Linux`,`OpenSUSE-42`,`SLES-12`,`FedoraRemix`。

如果尚未开启WSL，执行该命令会先开启WSL，用户需要在开启后重启一次系统，然后再次执行该命令。

### 卸载WSL发行版

```bat
> ezwsl uninstall -d Ubuntu-20.04
```

### 设置默认的发行版

```bat
> ezwsl set-default -d Ubuntu-20.04
```

默认情况下第一次安装的发行版会自动成为默认系统，如果想设置为其它系统，可以使用该命令。

### 设置默认的WSL版本

```bat
> ezwsl set-default-version -v 2
```

WSL默认使用的是WSL1，可以使用该命令修改默认的WSL版本。

升级WSL2需要开启`VirtualMachinePlatform`特性，如果尚未开启，工具会自动开启并提示重启系统。请在重启后再次执行该命令。

### 设置发行版使用的WSL版本

```bat
> ezwsl set-dist-version -d Ubuntu-20.04 -v 2
```

与`set-default-version`命令相比，该命令只是设置指定的发行版WSL版本，不会修改默认的WSL版本。使用该命令也需要开启`VirtualMachinePlatform`特性。

### 安装zsh

zsh是目前使用非常广泛的`shell`，这里提供了一键安装zsh的命令，并且会安装`oh-my-zsh`以及`Noto Mono for Powerline`字体。

```bat
> ezwsl install-zsh -p password -d Ubuntu-20.04 --theme agnoster --set-default-shell
```

`-p`是Linux系统的当前用户密码（必选）

`-d`是要安装的发行版名字，不指定则使用当前发行版（可选）

`--theme`是使用zsh主题，默认是`agnoster`（可选）

`--set-default-shell`表示设置默认的shell为zsh（可选）

### 安装命令行终端

```bat
> ezwsl install-terminal -n wsl-terminal -p password --install-path C:\ --default-shell /bin/zsh
```

`-n`是terminal名称，目前只支持`wsl-terminal`、`windows-terminal`（必选）

`-p`是当前Linux系统的当前用户密码（必选）

`--install-path`是安装路径，默认为`%APPDATA%`（可选，只对`wsl-terminal`有效）

`--default-shell`是终端默认使用的shell，默认是`bash`（可选）

### 端口转发

WSL2中，WSL中不能通过`回环地址`访问Windows中创建的TCP服务。因此，easywsl提供了端口转发能力，允许在WSL中像访问本地服务一样访问Windows上的服务。

```bat
> ezwsl forward -p password --ports 80;443
```

`-p`是当前Linux系统的当前用户密码（必选）

`--ports`是要转发的端口列表，端口间使用`;`分割
