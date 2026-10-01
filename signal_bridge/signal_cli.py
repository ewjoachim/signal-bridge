import json
import logging
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class SignalCliError(Exception):
    pass


@dataclass(frozen=True)
class SignalCli:
    account: str
    data_dir: Path

    def _run(self, *args: str, stdin: str | None = None) -> str:
        argv = [
            "signal-cli",
            "--config",
            str(self.data_dir),
            "-a",
            self.account,
            "-o",
            "json",
            *args,
        ]
        try:
            result = subprocess.run(
                argv,
                input=stdin,
                capture_output=True,
                text=True,
                check=True,
                timeout=300,
            )
        except subprocess.CalledProcessError as exc:
            raise SignalCliError(
                f"signal-cli {args[0]} failed: {exc.stderr.strip()}"
            ) from exc
        if result.stderr.strip():
            logger.info("signal-cli %s: %s", args[0], result.stderr.strip())
        return result.stdout

    def receive(self) -> list[dict]:
        output = self._run(
            "receive",
            "--timeout",
            "5",
            "--ignore-stories",
            "--ignore-stickers",
            "--ignore-avatars",
        )
        return [json.loads(line) for line in output.splitlines() if line.strip()]

    def send_to_group(
        self, group_id: str, text: str, attachments: Iterable[Path] = ()
    ) -> None:
        args = ["send", "-g", group_id, "--message-from-stdin"]
        if paths := [str(path) for path in attachments]:
            args += ["-a", *paths]
        self._run(*args, stdin=text)

    def attachment_path(self, attachment_id: str) -> Path:
        return self.data_dir / "attachments" / Path(attachment_id).name
