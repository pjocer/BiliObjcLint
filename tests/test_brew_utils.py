"""brew_utils 模块测试 - tap trust 检测与自动信任"""
import json
import subprocess
from unittest.mock import patch, MagicMock

from core.lint.brew_utils import is_tap_trusted, ensure_tap_trusted, DEFAULT_TAP


def _mk_result(returncode=0, stdout="", stderr=""):
    """构造 subprocess.run 返回的 mock result"""
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def _trust_json(taps):
    """构造 brew trust --json v1 的输出"""
    return json.dumps({"taps": taps, "formulae": [], "casks": [], "commands": []})


class TestIsTapTrusted:
    def test_trusted(self):
        with patch('core.lint.brew_utils.subprocess.run',
                   return_value=_mk_result(0, _trust_json([DEFAULT_TAP]))):
            assert is_tap_trusted() is True

    def test_not_trusted(self):
        with patch('core.lint.brew_utils.subprocess.run',
                   return_value=_mk_result(0, _trust_json([]))):
            assert is_tap_trusted() is False

    def test_other_tap_not_trusted(self):
        with patch('core.lint.brew_utils.subprocess.run',
                   return_value=_mk_result(0, _trust_json(["other/tap"]))):
            assert is_tap_trusted() is False

    def test_brew_below_6_returns_none(self):
        # brew < 6.0 无 trust 命令，退出码非 0
        with patch('core.lint.brew_utils.subprocess.run',
                   return_value=_mk_result(1, "", "Unknown command: trust")):
            assert is_tap_trusted() is None

    def test_brew_not_available_returns_none(self):
        with patch('core.lint.brew_utils.subprocess.run',
                   side_effect=FileNotFoundError("brew not found")):
            assert is_tap_trusted() is None

    def test_invalid_json_returns_none(self):
        with patch('core.lint.brew_utils.subprocess.run',
                   return_value=_mk_result(0, "not json")):
            assert is_tap_trusted() is None


class TestEnsureTapTrusted:
    def test_already_trusted_no_trust_call(self):
        with patch('core.lint.brew_utils.subprocess.run',
                   return_value=_mk_result(0, _trust_json([DEFAULT_TAP]))) as mock_run:
            assert ensure_tap_trusted() is True
        # 只调了 brew trust --json v1，没有调 brew trust <tap>
        assert mock_run.call_count == 1
        assert mock_run.call_args[0][0] == ['brew', 'trust', '--json', 'v1']

    def test_brew_below_6_skips(self):
        with patch('core.lint.brew_utils.subprocess.run',
                   return_value=_mk_result(1, "", "Unknown command")) as mock_run:
            assert ensure_tap_trusted() is True
        assert mock_run.call_count == 1  # 只检测，没执行 trust

    def test_not_trusted_dry_run(self):
        with patch('core.lint.brew_utils.subprocess.run',
                   return_value=_mk_result(0, _trust_json([]))) as mock_run:
            assert ensure_tap_trusted(dry_run=True) is True
        assert mock_run.call_count == 1  # dry_run 不执行 trust

    def test_not_trusted_execute_success(self):
        side_effects = [
            _mk_result(0, _trust_json([])),    # is_tap_trusted 检测：未信任
            _mk_result(0, "", ""),              # brew trust <tap>：成功
        ]
        with patch('core.lint.brew_utils.subprocess.run',
                   side_effect=side_effects) as mock_run:
            assert ensure_tap_trusted() is True
        assert mock_run.call_count == 2
        assert mock_run.call_args_list[1][0][0] == ['brew', 'trust', DEFAULT_TAP]

    def test_not_trusted_execute_failure(self):
        side_effects = [
            _mk_result(0, _trust_json([])),     # 未信任
            _mk_result(1, "", "trust failed"),  # brew trust 失败
        ]
        with patch('core.lint.brew_utils.subprocess.run', side_effect=side_effects):
            assert ensure_tap_trusted() is False

    def test_not_trusted_execute_exception(self):
        def side_effect(args, **kwargs):
            if args == ['brew', 'trust', '--json', 'v1']:
                return _mk_result(0, _trust_json([]))
            raise subprocess.TimeoutExpired(cmd=args, timeout=30)
        with patch('core.lint.brew_utils.subprocess.run', side_effect=side_effect):
            assert ensure_tap_trusted() is False

    def test_uses_injected_logger(self):
        logger = MagicMock()
        with patch('core.lint.brew_utils.subprocess.run',
                   return_value=_mk_result(0, _trust_json([DEFAULT_TAP]))):
            ensure_tap_trusted(logger=logger)
        logger.info.assert_called()
