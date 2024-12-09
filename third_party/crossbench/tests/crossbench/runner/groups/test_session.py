# Copyright 2024 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest
from typing import Optional
from unittest import mock

from crossbench.browsers.browser import Browser
from crossbench.helper.state import UnexpectedStateError
from crossbench.runner.groups.session import BrowserSessionRunGroup
from tests import test_helper
from tests.crossbench.runner.helper import (BaseRunnerTestCase, MockProbe,
                                            MockRun)


class BrowserSessionRunGroupTestCase(BaseRunnerTestCase):

  def setUp(self):
    super().setUp()
    self.root_dir = self.out_dir / "custom"
    self.runner = self.default_runner()

  def default_session(self,
                      browser: Optional[Browser] = None,
                      throw: bool = True):
    browser = browser or self.browsers[0]
    return BrowserSessionRunGroup(self.runner, browser, 0, self.root_dir, throw)

  def test_basic_properties(self):
    session = self.default_session()
    self.assertIs(session.runner, self.runner)
    self.assertEqual(session.index, 0)
    self.assertIs(session.browser, self.browsers[0])
    self.assertFalse(session.is_single_run)
    self.assertFalse(session.is_running)
    self.assertEqual(session.root_dir, self.root_dir)
    self.assertFalse(session.extra_flags)
    self.assertFalse(session.extra_js_flags)
    self.assertIn("0", str(session.info_stack))
    self.assertIn(str(self.browsers[0].unique_name), str(session.info_stack))
    self.assertEqual(session.info["runs"], 0)
    self.assertEqual(session.info["index"], 0)
    self.assertIn("0", str(session))
    self.assertIn(str(self.browsers[0]), str(session))
    self.assertTrue(session.browser_tmp_dir.is_dir())
    with self.assertRaises(IndexError):
      _ = session.timing

  def test_out_dir_single_run(self):
    session = self.default_session()
    with self.assertRaises(UnexpectedStateError):
      _ = session.out_dir
    run_1 = MockRun(self.runner, session, "run 1")
    session.append(run_1)
    with self.assertRaises(UnexpectedStateError):
      _ = session.out_dir
    session.set_ready()
    self.assertEqual(session.out_dir, run_1.out_dir)
    self.assertNotEqual(session.out_dir, session.raw_session_dir)

  def test_out_dir_mulitple_runs(self):
    session = self.default_session()
    run_1 = MockRun(self.runner, session, "run 1")
    run_2 = MockRun(self.runner, session, "run 2")
    session.append(run_1)
    session.append(run_2)
    session.set_ready()
    self.assertNotEqual(session.out_dir, run_1.out_dir)
    self.assertEqual(session.out_dir, session.raw_session_dir)

  def test_append(self):
    session = self.default_session()
    run_1 = MockRun(self.runner, session, "run 1")
    session.append(run_1)
    self.assertListEqual(list(session.runs), [run_1])
    self.assertEqual(session.info["runs"], 1)
    self.assertTrue(session.is_single_run)
    self.assertFalse(session.is_running)
    self.assertIs(session.first_run, run_1)
    self.assertIs(session.timing, run_1.timing)

    run_2 = MockRun(self.runner, session, "run 2")
    session.append(run_2)
    self.assertListEqual(list(session.runs), [run_1, run_2])
    self.assertEqual(session.info["runs"], 2)

    session.set_ready()
    self.assertFalse(session.is_single_run)
    self.assertFalse(session.is_running)
    self.assertIs(session.first_run, run_1)
    self.assertFalse(session.extra_flags)
    self.assertFalse(session.extra_js_flags)

    self.assertTrue(session.is_first_run(run_1))
    self.assertFalse(session.is_first_run(run_2))

  def test_append_after_ready(self):
    session = self.default_session()
    run_1 = MockRun(self.runner, session, "run 1")
    session.append(run_1)
    session.set_ready()
    with self.assertRaises(UnexpectedStateError):
      session.append(MockRun(self.runner, session, "run 3"))

  def test_append_wrong_session(self):
    session_1 = self.default_session()
    run_1 = MockRun(self.runner, session_1, "run 0")
    session_1.append(run_1)
    session_2 = self.default_session(self.browsers[1])
    run_2 = MockRun(self.runner, session_2, "run 0")
    with self.assertRaises(AssertionError):
      session_1.append(run_2)
    run_3 = MockRun(self.runner, session_1, "run 0")
    run_3.browser = self.browsers[1]
    with self.assertRaises(AssertionError):
      session_1.append(run_3)

  def test_append_different_probes(self):
    session = self.default_session()
    run_1 = MockRun(self.runner, session, "run 0")
    run_1.probes = []
    run_2 = MockRun(self.runner, session, "run 0")
    run_2.probes = [MockProbe()]
    session.append(run_1)
    session.append(run_2)
    with self.assertRaises(ValueError):
      session.set_ready()

  def test_set_ready(self):
    with self.assertRaises(ValueError):
      session = self.default_session()
      session.set_ready()
    session = self.default_session()
    session.append(MockRun(self.runner, session, "run 0"))
    session.set_ready()
    self.assertFalse(session.extra_flags)
    self.assertFalse(session.extra_js_flags)

  def test_open_not_ready(self):
    session = self.default_session()
    self.assertFalse(session.is_running)
    did_run = False
    with self.assertRaises(UnexpectedStateError):
      with session.open():
        did_run = True
    self.assertFalse(session.is_running)
    self.assertFalse(did_run)

  def test_open_not_ready_with_run(self):
    session = self.default_session()
    run = MockRun(self.runner, session, "run 0")
    session.append(run)
    self.assertFalse(session.is_running)
    did_run = False
    with self.assertRaises(UnexpectedStateError):
      with session.open():
        did_run = True
    self.assertFalse(session.is_running)
    self.assertTrue(session.is_success)
    self.assertFalse(run.did_setup)
    self.assertFalse(run.did_run)
    self.assertFalse(did_run)

  def test_open(self):
    session = self.default_session()
    run = MockRun(self.runner, session, "run 0")
    session.append(run)
    session.set_ready()
    self.assertFalse(session.is_running)
    self.assertFalse(run.did_setup)
    self.assertFalse(run.did_teardown)
    did_run = False
    with session.open() as startup_is_success:
      self.assertTrue(session.is_running)
      self.assertTrue(run.did_setup)
      self.assertTrue(session.browser.is_running)
      self.assertFalse(run.did_teardown_browser)
      self.assertTrue(session._probe_context_manager.is_running)
      # runs would be triggered here...
      did_run = True
    self.assertTrue(startup_is_success)
    self.assertFalse(session.is_running)
    self.assertFalse(session.browser.is_running)
    self.assertFalse(session._probe_context_manager.is_running)
    self.assertTrue(session.is_success)
    self.assertTrue(session.path.is_dir())
    self.assertTrue(run.did_setup)
    self.assertFalse(run.did_run)
    self.assertTrue(run.did_teardown_browser)
    self.assertTrue(did_run)

  def test_open_dry_run(self):
    session = self.default_session()
    run = MockRun(self.runner, session, "run 0")
    session.append(run)
    session.set_ready()
    self.assertFalse(session.is_running)
    did_run = False
    with session.open(is_dry_run=True) as startup_is_success:
      self.assertTrue(session.is_running)
      self.assertFalse(session.browser.is_running)
      self.assertTrue(session._probe_context_manager.is_running)
      # runs would be triggered here...
      did_run = True
    self.assertTrue(startup_is_success)
    self.assertFalse(session.is_running)
    self.assertFalse(session.browser.is_running)
    self.assertFalse(session._probe_context_manager.is_running)
    self.assertTrue(run.did_setup)
    self.assertFalse(run.did_teardown_browser)
    self.assertTrue(did_run)

  def test_open_inner_throw(self):
    session = self.default_session(throw=True)
    run = MockRun(self.runner, session, "run 0")
    session.append(run)
    session.set_ready()
    did_run = False
    with self.assertRaises(ValueError):
      with session.open() as startup_is_success:
        self.assertTrue(session.browser.is_running)
        self.assertFalse(run.did_teardown_browser)
        self.assertTrue(session._probe_context_manager.is_running)
        did_run = True
        raise ValueError("Test run failed")
    self.assertTrue(startup_is_success)
    self.assertTrue(did_run)
    self._validate_post_inner_throw(session, run)

  def _validate_post_inner_throw(self, session, run):
    # Startup succeed, the inner evaluation failed.
    self.assertFalse(session._probe_context_manager.is_running)
    self.assertFalse(session.browser.is_running)
    self.assertFalse(session.is_running)
    self.assertFalse(session.is_success)
    self.assertTrue(run.did_setup)
    self.assertTrue(run.did_teardown_browser)
    self.assertIn("Test run failed", str(session.exceptions[0].exception))

  def test_open_inner_throw_capture(self):
    session = self.default_session(throw=False)
    run = MockRun(self.runner, session, "run 0")
    session.append(run)
    session.set_ready()
    did_run = False
    with session.open() as startup_is_success:
      self.assertTrue(session.browser.is_running)
      self.assertFalse(run.did_teardown_browser)
      self.assertTrue(session._probe_context_manager.is_running)
      did_run = True
      raise ValueError("Test run failed")
    self.assertTrue(did_run)
    # Startup succeed, the inner evaluation failed.
    self.assertTrue(startup_is_success)
    self._validate_post_inner_throw(session, run)
    self.assertEqual(len(session.exceptions), 1)

  def test_open_network_error(self):
    session = self.default_session(throw=False)
    run = MockRun(self.runner, session, "run 0")
    session.append(run)
    session.set_ready()
    did_run = False
    with mock.patch.object(
        session.network,
        "open",
        side_effect=ValueError("Network startup error")):
      with session.open() as startup_is_success:
        # Due to how context managers work we run the inner code even if
        # the setup failed.
        self.assertFalse(startup_is_success)
        did_run = True
    self.assertTrue(did_run)
    self.assertEqual(len(session.exceptions), 1)
    self._validate_open_network_error(session, run)

  def test_open_network_error_throw(self):
    session = self.default_session(throw=True)
    run = MockRun(self.runner, session, "run 0")
    session.append(run)
    session.set_ready()
    did_run = False
    with self.assertRaises(ValueError) as cm:
      with mock.patch.object(
          session.network,
          "open",
          side_effect=ValueError("Network startup error")):
        with session.open():
          did_run = True
    self.assertFalse(did_run)
    self.assertIn("Network startup error", str(cm.exception))
    self._validate_open_network_error(session, run)

  def _validate_open_network_error(self, session, run):
    self.assertFalse(session._probe_context_manager.is_running)
    self.assertFalse(session.browser.is_running)
    self.assertFalse(session.is_running)
    self.assertFalse(session.is_success)
    self.assertTrue(run.did_setup)
    self.assertFalse(run.did_teardown_browser)
    self.assertIn("Network startup error", str(session.exceptions[0].exception))

if __name__ == "__main__":
  test_helper.run_pytest(__file__)
