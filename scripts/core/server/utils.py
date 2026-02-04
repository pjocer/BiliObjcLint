"""
BiliObjCLint Server - 工具函数
"""
from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import List, Tuple


def ensure_dir(path: Path) -> None:
    """确保目录存在"""
    path.mkdir(parents=True, exist_ok=True)


def default_config_path() -> Path:
    """默认配置文件路径"""
    return Path(os.path.expanduser("~/.biliobjclint/biliobjclint_server_config.json"))


def default_pid_path() -> Path:
    """默认 PID 文件路径"""
    return Path(os.path.expanduser("~/.biliobjclint/lintserver.pid"))


def project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent.parent.parent


def template_config_path() -> Path:
    """配置模板文件路径"""
    return project_root() / "config" / "biliobjclint_server_config.json"


def get_local_ips() -> List[Tuple[str, str]]:
    """获取本机所有网络接口的 IP 地址

    Returns:
        List of (interface_name, ip_address) tuples
    """
    ips: List[Tuple[str, str]] = []

    # 方法1: 通过连接外部地址获取主要 IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("8.8.8.8", 80))
        primary_ip = s.getsockname()[0]
        s.close()
        if primary_ip and primary_ip != "127.0.0.1":
            ips.append(("primary", primary_ip))
    except Exception:
        pass

    # 方法2: 通过 hostname 获取
    try:
        hostname = socket.gethostname()
        host_ips = socket.gethostbyname_ex(hostname)[2]
        for ip in host_ips:
            if ip != "127.0.0.1" and ("primary", ip) not in ips:
                ips.append(("hostname", ip))
    except Exception:
        pass

    # 方法3: 尝试获取所有网络接口 (macOS/Linux)
    try:
        import fcntl
        import struct
        import array

        def get_interface_ip(ifname: str) -> str:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            return socket.inet_ntoa(fcntl.ioctl(
                s.fileno(),
                0x8915,  # SIOCGIFADDR
                struct.pack('256s', ifname[:15].encode())
            )[20:24])

        # 获取所有接口名称
        max_interfaces = 128
        bytes_per_interface = 40
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        names = array.array('B', b'\0' * max_interfaces * bytes_per_interface)
        outbytes = struct.unpack('iL', fcntl.ioctl(
            s.fileno(),
            0x8912,  # SIOCGIFCONF
            struct.pack('iL', max_interfaces * bytes_per_interface, names.buffer_info()[0])
        ))[0]

        namestr = names.tobytes()
        for i in range(0, outbytes, bytes_per_interface):
            ifname = namestr[i:i+16].split(b'\0', 1)[0].decode()
            try:
                ip = get_interface_ip(ifname)
                if ip != "127.0.0.1" and not any(ip == existing[1] for existing in ips):
                    ips.append((ifname, ip))
            except Exception:
                pass
    except Exception:
        pass

    return ips


def get_primary_ip() -> str:
    """获取本机主要 IP 地址（用于显示）

    Returns:
        Primary IP address or "127.0.0.1" if not found
    """
    ips = get_local_ips()
    if ips:
        return ips[0][1]
    return "127.0.0.1"


def is_port_in_use(port: int, host: str = "0.0.0.0") -> bool:
    """检查端口是否被占用

    Args:
        port: 端口号
        host: 主机地址

    Returns:
        True if port is in use, False otherwise
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def find_process_using_port(port: int) -> Tuple[int, str]:
    """查找占用端口的进程

    Args:
        port: 端口号

    Returns:
        (pid, process_name) tuple, (0, "") if not found
    """
    import subprocess

    try:
        # macOS: lsof -i :port
        result = subprocess.run(
            ["lsof", "-i", f":{port}", "-t"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            pid = int(result.stdout.strip().split("\n")[0])
            # 获取进程名
            ps_result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "comm="],
                capture_output=True,
                text=True,
                timeout=5
            )
            proc_name = ps_result.stdout.strip() if ps_result.returncode == 0 else ""
            return pid, proc_name
    except Exception:
        pass

    return 0, ""
