"""
Portable MCP server lifecycle and asset downloader for Russian Roulette plugin.
Supports automatic downloading of prebuilt binaries from GitHub Releases and
managing the local in-process/background portable referee server.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import platform
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Optional

import aiohttp
from astrbot.api import logger

RELEASE_TAG = "v0.2.0"
REPO_OWNER = "AKIMOTOkaya"
REPO_NAME = "roulette-mcp-binaries"

# Direct release URLs with fallback mirrors for network reliability
PRIMARY_DOWNLOAD_URL = (
    f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/{RELEASE_TAG}"
)
# Ordered most-to-least reliable; verified reachable from the maintainer's
# network. `mirror.ghproxy.com` was dropped after it began timing out.
FALLBACK_MIRRORS = [
    f"https://ghfast.top/https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/{RELEASE_TAG}",
    f"https://ghproxy.net/https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/{RELEASE_TAG}",
]

# Archive name per (system, machine) pair. Keep this table as the single source
# of truth: the release publishes exactly these names, and `verify_release.py`
# in the binaries repo checks that the tag matches this table.
SUPPORTED_ASSETS = {
    ("linux", "x86_64"): "roulette-mcp-linux-x86_64.tar.gz",
    ("linux", "aarch64"): "roulette-mcp-linux-aarch64.tar.gz",
    ("linux", "armv7l"): "roulette-mcp-linux-armv7.tar.gz",
    ("darwin", "arm64"): "roulette-mcp-darwin-arm64.tar.gz",
    ("darwin", "x86_64"): "roulette-mcp-darwin-x86_64.tar.gz",
}

# `platform.machine()` returns several spellings for the same architecture.
_MACHINE_ALIASES = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "x64": "x86_64",
    "aarch64": "aarch64",
    "arm64": "aarch64",
    "armv8b": "aarch64",
    "armv8l": "aarch64",
    "armv7l": "armv7l",
    "armv7": "armv7l",
    "armhf": "armv7l",
}


def normalize_machine(machine: str) -> str:
    """Maps the many spellings of an architecture onto one canonical name."""
    lowered = machine.strip().lower()
    return _MACHINE_ALIASES.get(lowered, lowered)


def resolve_platform_asset(
    system: Optional[str] = None,
    machine: Optional[str] = None,
) -> Optional[str]:
    """Returns the release archive name for this platform, or None if unsupported.

    Both arguments exist so the mapping can be unit-tested without touching the
    host platform.
    """
    sys_name = (system if system is not None else platform.system()).strip().lower()
    mach = normalize_machine(machine if machine is not None else platform.machine())

    if sys_name == "darwin" and mach == "aarch64":
        # macOS reports "arm64"; the table is keyed that way for clarity.
        return SUPPORTED_ASSETS.get(("darwin", "arm64"))

    return SUPPORTED_ASSETS.get((sys_name, mach))


def supported_platforms_hint() -> str:
    """Human-readable list of platforms that have prebuilt binaries."""
    labels = {
        "roulette-mcp-linux-x86_64.tar.gz": "Linux x86_64",
        "roulette-mcp-linux-aarch64.tar.gz": "Linux aarch64 (树莓派 4/5)",
        "roulette-mcp-linux-armv7.tar.gz": "Linux armv7l (树莓派 2/3)",
        "roulette-mcp-darwin-arm64.tar.gz": "macOS Apple Silicon",
        "roulette-mcp-darwin-x86_64.tar.gz": "macOS Intel",
    }
    return "、".join(labels[name] for name in SUPPORTED_ASSETS.values())



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
            raise RuntimeError(
                f"当前系统平台 ({platform.system()} {platform.machine()}) 暂无预编译便携二进制。\n"
                f"支持的平台包括: {supported_platforms_hint()}。\n"
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

        # Verify against the release's sha256sums.txt before touching the archive.
        # This catches truncated or corrupted downloads that would otherwise
        # surface later as a confusing tar error.
        expected = await self._fetch_expected_checksum(asset_name)
        if expected:
            actual = self._sha256_of(tmp_archive)
            if actual != expected:
                tmp_archive.unlink(missing_ok=True)
                raise RuntimeError(
                    f"引擎压缩包校验失败：期望 {expected[:16]}…，实际 {actual[:16]}…。"
                    f"请重试，或手动切换至 remote 公网模式。"
                )
            logger.info("[roulette-portable] SHA256 校验通过")
        else:
            logger.warning("[roulette-portable] 未能获取 sha256sums.txt，跳过完整性校验")

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

    @staticmethod
    def _sha256_of(path: Path) -> str:
        """Returns the hex SHA256 digest of a file."""
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    async def _fetch_expected_checksum(self, asset_name: str) -> Optional[str]:
        """Fetches sha256sums.txt from the first reachable source and parses it."""
        urls = [f"{PRIMARY_DOWNLOAD_URL}/sha256sums.txt"] + [
            f"{mirror}/sha256sums.txt" for mirror in FALLBACK_MIRRORS
        ]
        async with aiohttp.ClientSession() as session:
            for url in urls:
                try:
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=15.0, connect=6.0)
                    ) as resp:
                        if resp.status != 200:
                            continue
                        text = await resp.text()
                except Exception as e:
                    logger.debug(f"[roulette-portable] 校验文件下载失败 {url}: {e}")
                    continue

                for line in text.splitlines():
                    parts = line.split()
                    if len(parts) == 2 and parts[1].lstrip("*") == asset_name:
                        return parts[0].strip().lower()
        return None

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
