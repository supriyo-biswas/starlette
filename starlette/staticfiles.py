import os
import stat

from aiofiles.os import stat as aio_stat

from starlette.responses import FileResponse, PlainTextResponse, Response
from starlette.types import ASGIInstance, Receive, Scope, Send


class StaticFiles:
    def __init__(self, *, directory: str, check_dir: bool = True) -> None:
        if check_dir and not os.path.isdir(directory):
            raise RuntimeError("Directory '%s' does not exist" % directory)
        self.directory = directory
        self.config_checked = False

    def __call__(self, scope: Scope) -> ASGIInstance:
        assert scope["type"] == "http"
        if scope["method"] not in ("GET", "HEAD"):
            return PlainTextResponse("Method Not Allowed", status_code=405)
        path = os.path.normpath(os.path.join(*scope["path"].split("/")))
        if path.startswith(".."):
            return PlainTextResponse("Not Found", status_code=404)
        path = os.path.join(self.directory, path)
        if self.config_checked:
            check_directory = None
        else:
            check_directory = self.directory
            self.config_checked = True
        return _StaticFilesResponder(scope, path=path, check_directory=check_directory)


class _StaticFilesResponder:
    def __init__(self, scope: Scope, path: str, check_directory: str = None) -> None:
        self.scope = scope
        self.path = path
        self.check_directory = check_directory

    async def check_directory_configured_correctly(self) -> None:
        """
        Perform a one-off configuration check that StaticFiles is actually
        pointed at a directory, so that we can raise loud errors rather than
        just returning 404 responses.
        """
        directory = self.check_directory
        try:
            stat_result = await aio_stat(directory)
        except FileNotFoundError:
            raise RuntimeError("StaticFiles directory '%s' does not exist." % directory)
        if not (stat.S_ISDIR(stat_result.st_mode) or stat.S_ISLNK(stat_result.st_mode)):
            raise RuntimeError("StaticFiles path '%s' is not a directory." % directory)

    async def __call__(self, receive: Receive, send: Send) -> None:
        if self.check_directory is not None:
            await self.check_directory_configured_correctly()

        try:
            stat_result = await aio_stat(self.path)
        except FileNotFoundError:
            response = PlainTextResponse("Not Found", status_code=404)  # type: Response
        else:
            mode = stat_result.st_mode
            if not stat.S_ISREG(mode):
                response = PlainTextResponse("Not Found", status_code=404)
            else:
                response = FileResponse(
                    self.path, stat_result=stat_result, method=self.scope["method"]
                )

        await response(receive, send)
