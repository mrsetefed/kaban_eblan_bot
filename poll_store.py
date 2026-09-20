import asyncio
import base64
import json
import logging
import os
from pathlib import Path

import httpx

STATE_PATH = "state/polls.json"
MAX_SAVE_ATTEMPTS = 4


class FileBackend:
    """Локальный файл. Годится для разработки: на Render диск стирается при перезапуске."""

    def __init__(self, path):
        self.path = Path(path)

    async def load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8")), None
        except FileNotFoundError:
            return {}, None

    async def save(self, data, version):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True, None


class GithubBackend:
    """Файл в ветке репозитория через GitHub Contents API. Переживает засыпание и перезапуск бота."""

    def __init__(self, token, repo, branch="schedule", path=STATE_PATH, client_factory=None):
        self.url = f"https://api.github.com/repos/{repo}/contents/{path}"
        self.branch = branch
        self.headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
        self.client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=20))

    async def load(self):
        async with self.client_factory() as client:
            response = await client.get(self.url, params={"ref": self.branch}, headers=self.headers)
        if response.status_code == 404:
            return {}, None
        response.raise_for_status()
        body = response.json()
        return json.loads(base64.b64decode(body["content"]).decode("utf-8")), body["sha"]

    async def save(self, data, version):
        payload = {
            "message": "update poll state",
            "content": base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")).decode(),
            "branch": self.branch,
        }
        if version:
            payload["sha"] = version
        async with self.client_factory() as client:
            response = await client.put(self.url, headers=self.headers, json=payload)
        if response.status_code in (200, 201):
            return True, response.json()["content"]["sha"]
        if response.status_code in (409, 422):
            return False, None  # версия файла устарела: кто-то записал раньше нас
        response.raise_for_status()
        return False, None


def create_store(path):
    """Хранилище-файл в ветке schedule (если есть GITHUB_TOKEN) или локальный файл для разработки."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        backend = GithubBackend(token, os.environ.get("GITHUB_REPO", "mrsetefed/kaban_eblan_bot"), path=path)
    else:
        logging.warning(f"GITHUB_TOKEN не задан: {path} хранится в локальном файле и пропадёт при перезапуске")
        backend = FileBackend(path)
    return PollStore(backend)


class PollStore:
    """Состояние в памяти, которое каждой правкой сохраняется в бэкенд.
    Память нужна, чтобы не ходить в GitHub за каждым чтением, а бэкенд — чтобы ничего не пропало при перезапуске."""

    def __init__(self, backend):
        self.backend = backend
        self._data = None
        self._version = None
        self._lock = asyncio.Lock()

    async def _reload(self):
        self._data, self._version = await self.backend.load()

    async def read(self) -> dict:
        if self._data is None:
            async with self._lock:
                if self._data is None:
                    await self._reload()
        return self._data

    async def mutate(self, change):
        """Применяет change(data) и сохраняет. При конфликте версий перечитывает состояние и применяет правку заново."""
        async with self._lock:
            for _ in range(MAX_SAVE_ATTEMPTS):
                if self._data is None:
                    await self._reload()
                change(self._data)
                ok, version = await self.backend.save(self._data, self._version)
                if ok:
                    self._version = version
                    return
                logging.warning("Конфликт версий состояния опросов, перечитываю и повторяю")
                self._data = None
        raise RuntimeError("Не удалось сохранить состояние опросов")
