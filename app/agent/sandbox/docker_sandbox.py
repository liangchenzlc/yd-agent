import io
import tempfile
import os
from dataclasses import dataclass

from app.config.settings import get_settings
from app.agent.exceptions import SandboxError


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


def run_code(code: str, timeout: int | None = None) -> SandboxResult:
    """在 Docker 沙箱中执行 Python 代码。"""
    settings = get_settings()

    if timeout is None:
        timeout = settings.code_timeout

    image = settings.sandbox_image

    # 将代码写入临时文件
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name

    try:
        import docker

        client = docker.from_env()
        container = client.containers.run(
            image=image,
            command=f"python /code.py",
            volumes={tmp_path: {"bind": "/code.py", "mode": "ro"}},
            working_dir="/",
            remove=True,
            stdout=True,
            stderr=True,
            detach=False,
        )
        # docker-py 同步 run 返回 bytes 或 Container
        if hasattr(container, "output"):
            stdout = container.output[0].decode("utf-8", errors="replace") if container.output[0] else ""
            stderr = container.output[1].decode("utf-8", errors="replace") if container.output[1] else ""
        else:
            stdout = container.decode("utf-8", errors="replace") if isinstance(container, bytes) else str(container)
            stderr = ""
        return SandboxResult(stdout=stdout, stderr=stderr, exit_code=0, timed_out=False)

    except docker.errors.ContainerError as e:
        stderr_text = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
        return SandboxResult(stdout="", stderr=stderr_text, exit_code=e.exit_status or 1, timed_out=False)

    except docker.errors.ImageNotFound:
        # 拉取镜像
        try:
            client.images.pull(image)
            return run_code(code, timeout)
        except Exception as pull_e:
            raise SandboxError(f"Docker 镜像 {image} 不存在且拉取失败: {pull_e}")

    except docker.errors.DockerException as e:
        raise SandboxError(f"Docker 执行失败: {e}")

    finally:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
