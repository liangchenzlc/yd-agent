import os
import tempfile
from dataclasses import dataclass

from app.agent.exceptions import SandboxError
from app.config.settings import get_settings


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


def run_code(code: str, timeout: int | None = None) -> SandboxResult:
    settings = get_settings()
    if timeout is None:
        timeout = settings.code_timeout

    image = settings.sandbox_image

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name

    container = None
    try:
        import requests
        import docker

        client = docker.from_env()
        container = client.containers.run(
            image=image,
            command="python /code.py",
            volumes={tmp_path: {"bind": "/code.py", "mode": "ro"}},
            working_dir="/",
            remove=False,
            stdout=True,
            stderr=True,
            detach=True,
        )

        try:
            result = container.wait(timeout=timeout)
        except requests.exceptions.ReadTimeout:
            container.kill()
            stdout_logs = container.logs(stdout=True, stderr=False)
            stderr_logs = container.logs(stdout=False, stderr=True)
            return SandboxResult(
                stdout=stdout_logs.decode("utf-8", errors="replace") if stdout_logs else "",
                stderr=stderr_logs.decode("utf-8", errors="replace") if stderr_logs else "",
                exit_code=124,
                timed_out=True,
            )

        stdout_logs = container.logs(stdout=True, stderr=False)
        stderr_logs = container.logs(stdout=False, stderr=True)
        stdout = stdout_logs.decode("utf-8", errors="replace") if stdout_logs else ""
        stderr = stderr_logs.decode("utf-8", errors="replace") if stderr_logs else ""
        exit_code = result.get("StatusCode", 0) if isinstance(result, dict) else 0
        return SandboxResult(stdout=stdout, stderr=stderr, exit_code=exit_code, timed_out=False)

    except docker.errors.ContainerError as e:
        stderr_text = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
        return SandboxResult(stdout="", stderr=stderr_text, exit_code=e.exit_status or 1, timed_out=False)

    except docker.errors.ImageNotFound:
        try:
            client.images.pull(image)
            return run_code(code, timeout)
        except Exception as pull_e:
            raise SandboxError(f"Docker image {image} missing and pull failed: {pull_e}") from pull_e

    except docker.errors.DockerException as e:
        raise SandboxError(f"Docker execution failed: {e}") from e

    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
