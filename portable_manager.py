"""
Portable MCP server lifecycle and asset downloader for Russian Roulette plugin.
Supports automatic downloading of prebuilt binaries from GitHub Releases and
managing the local in-process/background portable referee server.
"""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Optional

import aiohttp
from astrbot.api import logger

RELEASE_TAG = "v0.1.0"
REPO_OWNER = "AKIMOTOkaya"
REPO_NAME = "roulette-mcp-binaries"

# Direct release URLs with fallback mirrors for network reliability
PRIMARY_DOWNLOAD_URL = (
    f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/{RELEASE_TAG}"
)
FALLBACK_MIRRORS = [
    f"https://ghfast.top/https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/{RELEASE_TAG}",
    f"https://ghproxy.net/https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/{RELEASE_TAG}",
    f"https://mirror.ghproxy.com/https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/{RELEASE_TAG}",
]


def resolve_platform_asset() -> Optional[str]:
    """Detects system OS and machine architecture to determine binary package name."""
    sys_name = platform.system().lower()
    mach = platform.machine().lower()

    if sys_name == "linux":
        if mach in ("x86_64", "amd64"):
            return "roulette-mcp-linux-x86_64.tar.gz"
        elif mach in ("aarch64", "arm64", "armv8b", "armv8l"):
            return "roulette-mcp-linux-aarch64.tar.gz"

    return None


class PortableMcpManager:
    """Manages downloading, verifying and running the portable roulette-mcp server."""

    def __init__(self, data_dir: Optional[Path] = None, default_port: int = 8787):
        if data_dir is not None:
            self.bin_dir = Path(data_dir) / "bin"
        else:
            self.bin_dir = Path(__file__).resolve().parent / "data" / "bin"

        self.binary_path = self.bin_dir / "roulette-mcp"
        self.default_port = default_port
        self._process: Optional[asyncio.subprocess.Process] = None

    def get_binary_path(self) -> Path:
        return self.binary_path

    def is_binary_available(self) -> bool:
        return self.binary_path.exists() and os.access(self.binary_path, os.X_OK)

    async def check_health(self, port: int) -> bool:
        """Checks if a local roulette-mcp instance is already listening and responsive."""
        url = f"http://127.0.0.1:{port}/api/health"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=1.5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("status") == "ok"
        except Exception:
            return False
        return False

    async def download_binary(self) -> Path:
        """Downloads and extracts the prebuilt binary for the current platform."""
        asset_name = resolve_platform_asset()
        if not asset_name:
            supported = "Linux x86_64, Linux aarch64 (树莓派)"
            raise RuntimeError(
                f"当前系统平台 ({platform.system()} {platform.machine()}) 暂无预编译便携二进制。\n"
                f"支持的平台包括: {supported}。\n"
                f"建议在插件配置中将 mode 设置为 'remote' 并连接公网服务器。"
            )

        self.bin_dir.mkdir(parents=True, exist_ok=True)
        download_urls = [f"{PRIMARY_DOWNLOAD_URL}/{asset_name}"] + [
            f"{mirror}/{asset_name}" for mirror in FALLBACK_MIRRORS
        ]

        logger.info(f"[roulette-portable] 正在下载便携式游戏引擎: {asset_name} ...")
        tmp_archive: Optional[Path] = None

        async with aiohttp.ClientSession() as session:
            for url in download_urls:
                try:
                    logger.debug(f"[roulette-portable] 尝试下载地址: {url}")
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=30.0, connect=6.0)
                    ) as resp:
                        if resp.status != 200:
                            logger.warning(
                                f"[roulette-portable] 下载返回状态码 {resp.status}，尝试备用源"
                            )
                            continue

                        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp_f:
                            tmp_archive = Path(tmp_f.name)
                            while True:
                                chunk = await resp.content.read(64 * 1024)
                                if not chunk:
                                    break
                                tmp_f.write(chunk)

                        logger.info("[roulette-portable] 二进制压缩包下载完成，开始校验解压...")
                        break
                except Exception as e:
                    logger.warning(f"[roulette-portable] 从 {url} 下载失败: {e}，尝试下一个源")
                    if tmp_archive and tmp_archive.exists():
                        tmp_archive.unlink(missing_ok=True)
                        tmp_archive = None

        if not tmp_archive or not tmp_archive.exists():
            raise RuntimeError(
                f"无法从 GitHub Releases 下载预编译引擎 ({asset_name})，请检查网络连接或手动切换至 remote 公网模式。"
            )

        # Extract archive
        try:
            with tarfile.open(tmp_archive, "r:gz") as tar:
                # Security: prevent directory traversal
                for member in tar.getmembers():
                    if member.name.startswith("/") or ".." in member.name:
                        raise ValueError(f"不安全的文件解压路径: {member.name}")
                tar.extractall(path=self.bin_dir)

            # Locate the extracted executable
            extracted_bin = self.bin_dir / "roulette-mcp"
            if not extracted_bin.exists():
                # Check if it was extracted into a subfolder
                for p in self.bin_dir.glob("**/roulette-mcp"):
                    if p.is_file():
                        shutil.move(str(p), str(self.binary_path))
                        break

            if not self.binary_path.exists():
                raise FileNotFoundError("压缩包内未找到 roulette-mcp 二进制文件")

            # Make executable
            os.chmod(self.binary_path, 0o755)
            logger.info(f"[roulette-portable] 便携式引擎已就绪: {self.binary_path}")
            return self.binary_path
        finally:
            if tmp_archive and tmp_archive.exists():
                tmp_archive.unlink(missing_ok=True)

    async def ensure_running(self, port: Optional[int] = None) -> str:
        """
        Ensures the local roulette-mcp server is downloaded and running.
        Returns the base HTTP URL (e.g. 'http://127.0.0.1:8787').
        """
        target_port = port or self.default_port

        # 1. If already responsive, reuse existing process
        if await self.check_health(target_port):
            logger.info(f"[roulette-portable] 检测到本地服务已在端口 {target_port} 运行")
            return f"http://127.0.0.1:{target_port}"

        # 2. Ensure binary exists or download it
        if not self.is_binary_available():
            logger.info("[roulette-portable] 本地未检测到便携引擎，准备自动拉取...")
            await self.download_binary()

        # 3. Spawn child process
        logger.info(f"[roulette-portable] 正在启动本地便携引擎进程 (端口: {target_port})...")
        env = {
            **os.environ,
            "HOST": "127.0.0.1",
            "PORT": str(target_port),
        }

        self._process = await asyncio.create_subprocess_exec(
            str(self.binary_path),
            "--http",
            "--port",
            str(target_port),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # 4. Wait for health check with timeout
        for _ in range(25):  # Wait up to 5 seconds
            await asyncio.sleep(0.2)
            if await self.check_health(target_port):
                logger.info(f"[roulette-portable] 本地便携引擎启动成功: http://127.0.0.1:{target_port}")
                return f"http://127.0.0.1:{target_port}"

            if self._process.returncode is not None:
                stderr_output = ""
                if self._process.stderr:
                    err_bytes = await self._process.stderr.read()
                    stderr_output = err_bytes.decode(errors="replace")
                raise RuntimeError(
                    f"便携引擎进程异常退出 (退出码 {self._process.returncode}): {stderr_output}"
                )

        raise TimeoutError(f"便携引擎在端口 {target_port} 启动超时 (5s 未通过健康检查)")

    def terminate(self) -> None:
        """Gracefully terminates the child process if managed by this instance."""
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                logger.info("[roulette-portable] 已终止本地便携引擎进程")
            except Exception as e:
                logger.warning(f"[roulette-portable] 终止进程时发生异常: {e}")
