import asyncio
import base64
import json
import logging
import os
from pathlib import Path

import httpx

STATE_PATH = "state/polls.json"
MAX_SAVE_ATTEMPTS = 4
# Тот же репозиторий, что зашит в /upd и vlasuka. Переменную окружения GITHUB_REPO намеренно не читаем:
# если она на хостинге задана иначе, записи состояния молча уходили бы не туда.
GITHUB_REPO = "mrsetefed/kaban_eblan_bot"
STATE_BRANCH = "schedule"


class StorageError(RuntimeError):
    """Хранилище состояния ответило ошибкой. В тексте код ответа и начало тела, чтобы причину было видно в логах."""


def describe(response) -> str:
    return f"GitHub {response.request.method} {response.status_code}: {response.text[:200]}"


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

    def __init__(self, token, repo=GITHUB_REPO, branch=STATE_BRANCH, path=STATE_PATH, client_factory=None):
        self.url = f"https://api.github.com/repos/{repo}/contents/{path}"
        self.branch = branch
        self.headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
        self.client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=20))

    async def load(self):
        async with self.client_factory() as client:
            response = await client.get(self.url, params={"ref": self.branch}, headers=self.headers)
        if response.status_code == 404:
            return {}, None
        if response.status_code != 200:
            raise StorageError(describe(response))
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
        # 409, или 422 про sha: версия файла устарела, кто-то записал раньше нас. Остальные 422 это настоящая ошибка запроса
        if response.status_code == 409 or (response.status_code == 422 and "sha" in response.text.lower()):
            return False, None
        raise StorageError(describe(response))


async def check_storage(client_factory=None) -> str:
    """Один запрос к GitHub при старте: понятная строка в логах, работает ли запись состояния."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return "⚠️ Хранилище состояния: GITHUB_TOKEN не задан, данные хранятся локально и пропадут при перезапуске"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    factory = client_factory or (lambda: httpx.AsyncClient(timeout=20))
    try:
        async with factory() as client:
            repo = await client.get(f"https://api.github.com/repos/{GITHUB_REPO}", headers=headers)
            if repo.status_code != 200:
                return f"❌ Хранилище состояния: репозиторий {GITHUB_REPO} недоступен ({describe(repo)})"
            if repo.json().get("permissions", {}).get("push") is False:
                return f"❌ Хранилище состояния: у токена нет права записи в {GITHUB_REPO}"
            branch = await client.get(f"https://api.github.com/repos/{GITHUB_REPO}/branches/{STATE_BRANCH}", headers=headers)
            if branch.status_code != 200:
                return f"❌ Хранилище состояния: ветка {STATE_BRANCH} недоступна ({describe(branch)})"
    except Exception as e:
        return f"❌ Хранилище состояния: не удалось связаться с GitHub ({e})"
    return f"✅ Хранилище состояния: {GITHUB_REPO}, ветка {STATE_BRANCH}, запись разрешена"


def create_store(path):
    """Хранилище-файл в ветке schedule (если есть GITHUB_TOKEN) или локальный файл для разработки."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        backend = GithubBackend(token, GITHUB_REPO, path=path)
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
        raise StorageError(f"не удалось сохранить: {MAX_SAVE_ATTEMPTS} конфликта версий подряд")
