# Copyright 2022 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import annotations

import abc
import contextlib
import copy
import pathlib
from typing import (TYPE_CHECKING, Any, Iterator, List, Optional, Tuple, Type,
                    cast)

from crossbench import plt
from crossbench.browsers.all import Chrome, Chromium, Edge, Firefox, Safari
from crossbench.browsers.attributes import BrowserAttributes
from crossbench.browsers.browser import Browser
from crossbench.browsers.settings import Settings
from crossbench.flags.chrome import ChromeFeatures, ChromeFlags
from crossbench.flags.js_flags import JSFlags
from crossbench.network.base import Network
from crossbench.plt.android_adb import AndroidAdbPlatform

if TYPE_CHECKING:
  import datetime as dt

  from crossbench.flags.base import Flags
  from crossbench.runner.groups import BrowserSessionRunGroup
  from crossbench.runner.runner import Runner


class MockNetwork(Network):

  @contextlib.contextmanager
  def open(self, session: BrowserSessionRunGroup) -> Iterator[Network]:
    with super().open(session):
      assert session.browser.network is self
      yield self
      assert self.is_running


class MockBrowser(Browser, metaclass=abc.ABCMeta):
  MACOS_BIN_NAME: str = ""
  VERSION: str = "100.22.33.44"

  @classmethod
  @abc.abstractmethod
  def mock_app_path(cls, platform: plt.Platform) -> pathlib.Path:
    pass

  @classmethod
  def setup_fs(cls, fs, platform: plt.Platform = plt.PLATFORM) -> None:
    app_path = cls.mock_app_path(platform)
    macos_bin_name = app_path.stem
    if cls.MACOS_BIN_NAME:
      macos_bin_name = cls.MACOS_BIN_NAME
    cls.setup_bin(fs, app_path, macos_bin_name, platform)

  @classmethod
  def setup_bin(cls,
                fs,
                bin_path: pathlib.Path,
                macos_bin_name: str,
                platform: plt.Platform = plt.PLATFORM) -> None:
    if platform.is_macos:
      assert bin_path.suffix == ".app"
      bin_path = bin_path / "Contents" / "MacOS" / macos_bin_name
    elif platform.is_win:
      assert bin_path.suffix == ".exe"
    if not bin_path.exists():
      fs.create_file(bin_path)

  @classmethod
  def default_flags(cls,
                    initial_data: Flags.InitialDataType = None) -> ChromeFlags:
    return ChromeFlags(initial_data)

  def __init__(self,
               label: str,
               path: Optional[pathlib.Path] = None,
               settings: Optional[Settings] = None):
    settings = settings or Settings()
    platform = settings.platform
    path = path or self.mock_app_path(platform)
    self.app_path = path
    if maybe_driver := settings.driver_path:
      assert isinstance(maybe_driver, pathlib.Path) and maybe_driver.exists()
    super().__init__(label, path, settings=settings)
    self.url_list: List[str] = []
    self.js_list: List[str] = []
    self.js_side_effects: List[Any] = []
    self.did_run: bool = False
    self.clear_cache_dir: bool = False

  def clear_cache(self, runner: Runner) -> None:
    pass

  def start(self, session: BrowserSessionRunGroup) -> None:
    assert not self._is_running
    self._is_running = True
    self.did_run = True

  def force_quit(self) -> None:
    if not self._is_running:
      return
    self._is_running = False

  def _extract_version(self) -> str:
    return self.VERSION

  def user_agent(self, runner: Runner) -> str:
    return f"Mock Browser {self.type_name}, {self.VERSION}"

  def show_url(self, runner: Runner, url, target: Optional[str] = None) -> None:
    self.url_list.append(url)

  def js(self,
         runner: Runner,
         script,
         timeout: Optional[dt.timedelta] = None,
         arguments=()):
    self.js_list.append(script)
    if timeout:
      assert timeout.total_seconds() > 0
    if self.js_side_effects is None:
      return None
    assert self.js_side_effects, ("Not enough mock js_side_effect available. "
                                  "Please add another js_side_effect entry for "
                                  f"arguments={arguments} \n"
                                  f"Script: {script}")
    result = self.js_side_effects.pop(0)
    # Return copies to avoid leaking data between repetitions.
    return copy.deepcopy(result)


def app_root(platform: plt.Platform) -> pathlib.Path:
  if platform.is_macos:
    return pathlib.Path("/Applications")
  if platform.is_win:
    return pathlib.Path("C:/Program Files")
  return pathlib.Path("/usr/bin")


class MockChromiumBrowser(MockBrowser, metaclass=abc.ABCMeta):

  @property
  def chrome_flags(self) -> ChromeFlags:
    chrome_flags = cast(ChromeFlags, self.flags)
    assert isinstance(chrome_flags, ChromeFlags)
    return chrome_flags

  @property
  def js_flags(self) -> JSFlags:
    return self.chrome_flags.js_flags

  @property
  def features(self) -> ChromeFeatures:
    return self.chrome_flags.features

  @property
  def attributes(self) -> BrowserAttributes:
    return BrowserAttributes.CHROMIUM | BrowserAttributes.CHROMIUM_BASED


# Inject MockBrowser into the browser hierarchy for easier testing.
Chromium.register(MockChromiumBrowser)


class MockChromeBrowser(MockChromiumBrowser, metaclass=abc.ABCMeta):

  @property
  def type_name(self) -> str:
    return "chrome"

  @property
  def attributes(self) -> BrowserAttributes:
    return BrowserAttributes.CHROME | BrowserAttributes.CHROMIUM_BASED


Chrome.register(MockChromeBrowser)
if not TYPE_CHECKING:
  assert issubclass(MockChromeBrowser, Chrome)


class MockChromeStable(MockChromeBrowser):

  @classmethod
  def mock_app_path(cls, platform: plt.Platform = plt.PLATFORM) -> pathlib.Path:
    if platform.is_macos:
      return app_root(platform) / "Google Chrome.app"
    if platform.is_win:
      return app_root(platform) / "Google/Chrome/Application/chrome.exe"
    return app_root(platform) / "google-chrome"


if not TYPE_CHECKING:
  assert issubclass(MockChromeStable, Chromium)
  assert issubclass(MockChromeStable, Chrome)


class MockChromeAndroidStable(MockChromeStable):

  @property
  def platform(self) -> AndroidAdbPlatform:
    assert isinstance(
        self._platform,
        AndroidAdbPlatform), (f"Invalid platform: {self._platform}")
    return cast(AndroidAdbPlatform, self._platform)

  def _resolve_binary(self, path: pathlib.Path) -> pathlib.Path:
    return path

  @property
  def attributes(self) -> BrowserAttributes:
    return (BrowserAttributes.CHROME | BrowserAttributes.CHROMIUM_BASED
            | BrowserAttributes.MOBILE)


class MockChromeBeta(MockChromeBrowser):
  VERSION = "101.22.33.44"

  @classmethod
  def mock_app_path(cls, platform: plt.Platform = plt.PLATFORM) -> pathlib.Path:
    if platform.is_macos:
      return app_root(platform) / "Google Chrome Beta.app"
    if platform.is_win:
      return app_root(platform) / "Google/Chrome Beta/Application/chrome.exe"
    return app_root(platform) / "google-chrome-beta"


class MockChromeDev(MockChromeBrowser):
  VERSION = "102.22.33.44"

  @classmethod
  def mock_app_path(cls, platform: plt.Platform = plt.PLATFORM) -> pathlib.Path:
    if platform.is_macos:
      return app_root(platform) / "Google Chrome Dev.app"
    if platform.is_win:
      return app_root(platform) / "Google/Chrome Dev/Application/chrome.exe"
    return app_root(platform) / "google-chrome-unstable"


class MockChromeCanary(MockChromeBrowser):
  VERSION = "103.22.33.44"

  @classmethod
  def mock_app_path(cls, platform: plt.Platform = plt.PLATFORM) -> pathlib.Path:
    if platform.is_macos:
      return app_root(platform) / "Google Chrome Canary.app"
    if platform.is_win:
      return app_root(platform) / "Google/Chrome SxS/Application/chrome.exe"
    return app_root(platform) / "google-chrome-canary"


class MockEdgeBrowser(MockChromiumBrowser, metaclass=abc.ABCMeta):

  @property
  def type_name(self) -> str:
    return "edge"

  @property
  def attributes(self) -> BrowserAttributes:
    return BrowserAttributes.EDGE | BrowserAttributes.CHROMIUM_BASED

Edge.register(MockEdgeBrowser)
if not TYPE_CHECKING:
  assert issubclass(MockEdgeBrowser, Chromium)
  assert issubclass(MockEdgeBrowser, Edge)


class MockEdgeStable(MockEdgeBrowser):

  @classmethod
  def mock_app_path(cls, platform: plt.Platform = plt.PLATFORM) -> pathlib.Path:
    if platform.is_macos:
      return app_root(platform) / "Microsoft Edge.app"
    if platform.is_win:
      return app_root(platform) / "Microsoft/Edge/Application/msedge.exe"
    return app_root(platform) / "microsoft-edge"


class MockEdgeBeta(MockEdgeBrowser):
  VERSION = "101.22.33.44"

  @classmethod
  def mock_app_path(cls, platform: plt.Platform = plt.PLATFORM) -> pathlib.Path:
    if platform.is_macos:
      return app_root(platform) / "Microsoft Edge Beta.app"
    if platform.is_win:
      return app_root(platform) / "Microsoft/Edge Beta/Application/msedge.exe"
    return app_root(platform) / "microsoft-edge-beta"


class MockEdgeDev(MockEdgeBrowser):
  VERSION = "102.22.33.44"

  @classmethod
  def mock_app_path(cls, platform: plt.Platform = plt.PLATFORM) -> pathlib.Path:
    if platform.is_macos:
      return app_root(platform) / "Microsoft Edge Dev.app"
    if platform.is_win:
      return app_root(platform) / "Microsoft/Edge Dev/Application/msedge.exe"
    return app_root(platform) / "microsoft-edge-dev"


class MockEdgeCanary(MockEdgeBrowser):
  VERSION = "103.22.33.44"

  @classmethod
  def mock_app_path(cls, platform: plt.Platform = plt.PLATFORM) -> pathlib.Path:
    if platform.is_macos:
      return app_root(platform) / "Microsoft Edge Canary.app"
    if platform.is_win:
      return app_root(platform) / "Microsoft/Edge SxS/Application/msedge.exe"
    return app_root(platform) / "unsupported/msedge-canary"


class MockSafariBrowser(MockBrowser, metaclass=abc.ABCMeta):

  @property
  def type_name(self) -> str:
    return "safari"

  @property
  def attributes(self) -> BrowserAttributes:
    return BrowserAttributes.SAFARI



Safari.register(MockSafariBrowser)
if not TYPE_CHECKING:
  assert issubclass(MockSafariBrowser, Safari)


class MockSafari(MockSafariBrowser):

  @classmethod
  def mock_app_path(cls, platform: plt.Platform = plt.PLATFORM) -> pathlib.Path:
    if platform.is_macos:
      return app_root(platform) / "Safari.app"
    if platform.is_win:
      return app_root(platform) / "Unsupported/Safari.exe"
    return pathlib.Path("/unsupported-platform/Safari")


class MockSafariTechnologyPreview(MockSafariBrowser):

  @classmethod
  def mock_app_path(cls, platform: plt.Platform = plt.PLATFORM) -> pathlib.Path:
    if platform.is_macos:
      return app_root(platform) / "Safari Technology Preview.app"
    if platform.is_win:
      return app_root(platform) / "Unsupported/Safari Technology Preview.exe"
    return pathlib.Path("/unsupported-platform/Safari Technology Preview")


class MockFirefoxBrowser(MockBrowser, metaclass=abc.ABCMeta):

  @property
  def type_name(self) -> str:
    return "firefox"

  @property
  def attributes(self) -> BrowserAttributes:
    return BrowserAttributes.FIREFOX


Firefox.register(MockFirefoxBrowser)
if not TYPE_CHECKING:
  assert issubclass(MockFirefoxBrowser, Firefox)


class MockFirefox(MockFirefoxBrowser):

  @classmethod
  def mock_app_path(cls, platform: plt.Platform = plt.PLATFORM) -> pathlib.Path:
    if platform.is_macos:
      return app_root(platform) / "Firefox.app"
    if platform.is_win:
      return app_root(platform) / "Mozilla Firefox/firefox.exe"
    return app_root(platform) / "firefox"


class MockFirefoxDeveloperEdition(MockFirefoxBrowser):

  @classmethod
  def mock_app_path(cls, platform: plt.Platform = plt.PLATFORM) -> pathlib.Path:
    if platform.is_macos:
      return app_root(platform) / "Firefox Developer Edition.app"
    if platform.is_win:
      return app_root(platform) / "Firefox Developer Edition/firefox.exe"
    return app_root(platform) / "firefox-developer-edition"


class MockFirefoxNightly(MockFirefoxBrowser):

  @classmethod
  def mock_app_path(cls, platform: plt.Platform = plt.PLATFORM) -> pathlib.Path:
    if platform.is_macos:
      return app_root(platform) / "Firefox Nightly.app"
    if platform.is_win:
      return app_root(platform) / "Firefox Nightly/firefox.exe"
    return app_root(platform) / "firefox-trunk"


ALL: Tuple[Type[MockBrowser], ...] = (
    MockChromeCanary,
    MockChromeDev,
    MockChromeBeta,
    MockChromeStable,
    MockEdgeCanary,
    MockEdgeDev,
    MockEdgeBeta,
    MockEdgeStable,
    MockSafari,
    MockSafariTechnologyPreview,
    MockFirefox,
    MockFirefoxDeveloperEdition,
    MockFirefoxNightly,
)
