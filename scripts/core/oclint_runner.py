"""
OCLint Runner Module - OCLint 调用封装
"""
import subprocess
import json
import os
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional

from .reporter import Violation, Severity
from .config import OCLintConfig
from .logger import get_logger


class OCLintRunner:
    """OCLint 执行器"""

    def __init__(self, project_root: str, config: OCLintConfig):
        self.project_root = Path(project_root)
        self.config = config
        self.logger = get_logger("biliobjclint")
        self.oclint_path = self._find_oclint()
        self.logger.debug(f"OCLintRunner initialized, oclint_path={self.oclint_path}")

    def _find_oclint(self) -> Optional[str]:
        """查找 OCLint 可执行文件"""
        # 优先使用本地编译的版本
        local_oclint = self.project_root / "BiliObjCLint" / "build" / "bin" / "oclint"
        if local_oclint.exists():
            return str(local_oclint)

        # 检查项目目录
        project_oclint = self.project_root / "build" / "bin" / "oclint"
        if project_oclint.exists():
            return str(project_oclint)

        # 检查系统 PATH
        try:
            result = subprocess.run(['which', 'oclint'], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass

        # 检查 Homebrew 安装
        homebrew_path = "/usr/local/bin/oclint"
        if os.path.exists(homebrew_path):
            return homebrew_path

        homebrew_arm_path = "/opt/homebrew/bin/oclint"
        if os.path.exists(homebrew_arm_path):
            return homebrew_arm_path

        return None

    def is_available(self) -> bool:
        """检查 OCLint 是否可用"""
        return self.oclint_path is not None

    def run(self, files: List[str], compile_commands_path: Optional[str] = None) -> List[Violation]:
        """
        运行 OCLint 检查

        Args:
            files: 要检查的文件列表
            compile_commands_path: compile_commands.json 路径
        Returns:
            违规列表
        """
        self.logger.info(f"Running OCLint on {len(files)} files")

        if not self.is_available():
            self.logger.warning("OCLint not available, skipping")
            return []

        if not files:
            self.logger.debug("No files to check")
            return []

        violations = []

        # 为每个文件单独运行（避免依赖 compile_commands.json）
        for i, file_path in enumerate(files):
            self.logger.debug(f"Checking file {i+1}/{len(files)}: {file_path}")
            file_violations = self._run_single_file(file_path)
            violations.extend(file_violations)

        self.logger.info(f"OCLint found {len(violations)} violations")
        return violations

    def _run_single_file(self, file_path: str) -> List[Violation]:
        """对单个文件运行 OCLint"""
        violations = []

        try:
            # 构建命令
            cmd = [self.oclint_path]

            # 添加规则配置
            for rule_config in self.config.rule_configurations:
                cmd.extend(['-rc', f"{rule_config['key']}={rule_config['value']}"])

            # 启用的规则
            for rule in self.config.enable_rules:
                cmd.extend(['-rule', rule])

            # 禁用的规则
            for rule in self.config.disable_rules:
                cmd.extend(['-disable-rule', rule])

            # 输出 JSON 格式
            cmd.extend(['-report-type', 'json'])

            # 源文件
            cmd.append(file_path)

            # 添加编译器参数（使用 -- 分隔）
            cmd.append('--')

            # ObjC 编译参数
            cmd.extend([
                '-x', 'objective-c',
                '-isysroot', self._get_sdk_path(),
                '-fmodules',
                '-fobjc-arc',
                '-Wall',
            ])

            # 添加常用的头文件搜索路径
            cmd.extend(['-I', str(self.project_root)])

            # 执行
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60  # 单文件 60 秒超时
            )

            # 解析 JSON 输出
            if result.stdout:
                violations.extend(self._parse_json_output(result.stdout, file_path))

        except subprocess.TimeoutExpired:
            pass  # 超时跳过
        except Exception as e:
            pass  # 其他错误跳过

        return violations

    def _get_sdk_path(self) -> str:
        """获取 SDK 路径"""
        try:
            result = subprocess.run(
                ['xcrun', '--show-sdk-path'],
                capture_output=True,
                text=True
            )
            return result.stdout.strip()
        except:
            return "/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator.sdk"

    def _parse_json_output(self, json_output: str, file_path: str) -> List[Violation]:
        """解析 OCLint JSON 输出"""
        violations = []

        try:
            # OCLint 可能输出非 JSON 内容，需要找到 JSON 部分
            json_start = json_output.find('{')
            if json_start == -1:
                return violations

            json_str = json_output[json_start:]
            data = json.loads(json_str)

            for violation_data in data.get('violation', []):
                severity = self._map_priority_to_severity(violation_data.get('priority', 3))

                v = Violation(
                    file_path=violation_data.get('path', file_path),
                    line=violation_data.get('startLine', 1),
                    column=violation_data.get('startColumn', 1),
                    severity=severity,
                    message=violation_data.get('message', 'Unknown issue'),
                    rule_id=violation_data.get('rule', 'unknown'),
                    source='oclint'
                )
                violations.append(v)

        except json.JSONDecodeError:
            pass

        return violations

    def _map_priority_to_severity(self, priority: int) -> Severity:
        """将 OCLint 优先级映射到严重级别"""
        if priority == 1:
            return Severity.ERROR
        elif priority == 2:
            return Severity.WARNING
        else:
            return Severity.WARNING

    def run_with_compile_commands(self, files: List[str], compile_commands: Dict[str, Any]) -> List[Violation]:
        """
        使用 compile_commands.json 运行（更准确但需要生成编译数据库）

        Args:
            files: 要检查的文件列表
            compile_commands: 编译命令数据
        Returns:
            违规列表
        """
        if not self.is_available() or not files:
            return []

        violations = []

        # 创建临时的 compile_commands.json
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(compile_commands, f)
            compile_commands_path = f.name

        try:
            cmd = [
                self.oclint_path,
                '-p', os.path.dirname(compile_commands_path),
                '-report-type', 'json'
            ]

            # 添加规则配置
            for rule_config in self.config.rule_configurations:
                cmd.extend(['-rc', f"{rule_config['key']}={rule_config['value']}"])

            # 添加文件
            cmd.extend(files)

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.stdout:
                for file_path in files:
                    violations.extend(self._parse_json_output(result.stdout, file_path))

        except Exception:
            pass
        finally:
            os.unlink(compile_commands_path)

        return violations


def generate_compile_commands(project_root: str, files: List[str]) -> List[Dict[str, str]]:
    """
    生成简单的 compile_commands.json 内容

    对于没有使用 xcodebuild 生成编译数据库的项目，
    可以使用这个函数生成一个基础的编译命令列表
    """
    sdk_path = "/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator.sdk"

    try:
        result = subprocess.run(['xcrun', '--show-sdk-path'], capture_output=True, text=True)
        if result.returncode == 0:
            sdk_path = result.stdout.strip()
    except:
        pass

    commands = []
    for file_path in files:
        commands.append({
            "directory": project_root,
            "file": file_path,
            "command": f"clang -x objective-c -isysroot {sdk_path} -fmodules -fobjc-arc -c {file_path}"
        })

    return commands
