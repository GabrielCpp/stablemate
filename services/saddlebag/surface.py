"""saddlebag run in a sandbox, over a keyring session of its own."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time

from ostler.book import CommandSurface, Environment, Seed

from .model.files import SEEDED

SEED = Seed(
    {
        "config.toml": "config_version = 2\n",
        "home/.keep": "",
        "run/.keep": "",
        "data/.keep": "",
        **SEEDED,
    },
    name="acme",
)

ENVIRONMENT = {
    "HOME": "<sandbox>/home",
    "STABLEMATE_CONFIG": "<sandbox>/config.toml",
    "XDG_RUNTIME_DIR": "<sandbox>/run",
    "XDG_STATE_HOME": "<sandbox>/home/state",
    "XDG_CONFIG_HOME": "<sandbox>/home/config",
}

PASSWORD = "unlocks the keyring\n"
PATH = ":".join((os.path.dirname(shutil.which("saddlebag") or "/usr/bin/saddlebag"), "/usr/local/bin", "/usr/bin", "/bin"))


class Session:
    """The desktop session a keyring needs: a message bus and the secret service on it, alive for one world."""

    def __init__(self) -> None:
        self.folder: str | None = None
        self.bus: subprocess.Popen[bytes] | None = None
        self.keyring: subprocess.Popen[bytes] | None = None

    def start(self) -> dict[str, str]:
        self.end()
        self.folder = tempfile.mkdtemp(prefix="saddlebag-session-")
        address = f"unix:path={self.folder}/bus"
        env = {**os.environ, "DBUS_SESSION_BUS_ADDRESS": address, "XDG_RUNTIME_DIR": self.folder,
               "XDG_DATA_HOME": f"{self.folder}/data", "HOME": self.folder}
        os.makedirs(f"{self.folder}/data")
        self.bus = subprocess.Popen(["dbus-daemon", "--session", "--nofork", f"--address={address}"], env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        socket = f"{self.folder}/bus"
        for _ in range(500):
            if os.path.exists(socket):
                break
            time.sleep(0.01)
        self.keyring = subprocess.Popen(["gnome-keyring-daemon", "--foreground", "--unlock", "--components=secrets"],
                                        env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL)
        assert self.keyring.stdin is not None
        self.keyring.stdin.write(PASSWORD.encode())
        self.keyring.stdin.close()
        time.sleep(0.25)
        return {"DBUS_SESSION_BUS_ADDRESS": address}

    def end(self) -> None:
        for process in (self.keyring, self.bus):
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait()
        self.keyring = self.bus = None
        if self.folder is not None:
            shutil.rmtree(self.folder, ignore_errors=True)
            self.folder = None


class SaddlebagCli(CommandSurface):
    def __init__(self, environment: Environment):
        self.session = Session()
        self.variables = dict(ENVIRONMENT)
        super().__init__(SEED, self.variables)

    def restore(self) -> None:
        super().restore()
        env = self.command_client.sandboxed().env
        env.update(self.session.start())
        env["PATH"] = PATH
        env["XDG_DATA_HOME"] = f"{self.session.folder}/data"

    def stop(self) -> None:
        self.session.end()
        super().stop()
