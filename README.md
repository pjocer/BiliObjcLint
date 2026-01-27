# BiliObjCLint

Objective-C 代码规范检查工具，支持增量检查、Xcode 集成和 Claude AI 自动修复。

## Features

- **Incremental Check**: Only check Git-changed code for fast and efficient linting
- **Xcode Integration**: Output native Xcode warning/error format
- **Dual Engine Architecture**:
  - OCLint: 70+ built-in rules with deep AST analysis
  - Python Rule Engine: Lightweight, fast, and easy to extend
- **Claude AI Auto-fix**: Automatically fix code issues with Claude Code CLI
- **Highly Configurable**: YAML configuration file for flexible rule customization
- **Easy to Extend**: Support both Python and C++ custom rules

## Requirements

- macOS 10.15+
- Python 3.9+
- Xcode 12+ (for Xcode integration)
- Git (for incremental checking)

## Installation

### Via Homebrew (Recommended)

```bash
brew tap bilibili/tap
brew install biliobjclint
```

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/bilibili/BiliObjCLint.git
cd BiliObjCLint

# Initialize Python virtual environment
./scripts/setup_env.sh
```

## Quick Start

### 1. Basic Usage

```bash
# Check all files
biliobjclint

# Incremental check (only Git changes)
biliobjclint --incremental

# Check specific files
biliobjclint --files path/to/File.m

# Verbose output
biliobjclint --verbose
```

### 2. Xcode Integration

```bash
# Run the installation script
./scripts/install_xcode.sh /path/to/your/project.xcodeproj

# Or specify a target
./scripts/install_xcode.sh /path/to/your/project.xcodeproj --target YourTarget
```

This will:
1. Add a Build Phase script to your Xcode project
2. Copy the default configuration file to your project root

### 3. Build OCLint (Optional)

If you need OCLint's deep AST analysis:

```bash
# Build from source
./scripts/build_oclint.sh

# Or install via Homebrew
brew install oclint
```

## Configuration

Create `.biliobjclint.yaml` in your project root:

```yaml
# Basic settings
base_branch: "origin/master"
incremental: true
fail_on_error: true

# File filtering
excluded:
  - "Pods/**"
  - "Vendor/**"
  - "ThirdParty/**"

# Python rules
python_rules:
  class_prefix:
    enabled: true
    severity: warning
    params:
      prefix: "BL"

  weak_delegate:
    enabled: true
    severity: error

  line_length:
    enabled: true
    params:
      max_length: 120

# OCLint settings
oclint:
  enabled: true
  rule_configurations:
    - key: LONG_METHOD
      value: 80
    - key: CYCLOMATIC_COMPLEXITY
      value: 10

# Claude auto-fix settings
claude_autofix:
  trigger: "any"     # any | error | disable
  mode: "silent"     # silent | terminal | vscode
  timeout: 120
```

See `config/default.yaml` for a complete example.

## Built-in Rules

### Python Rules

| Rule ID | Description | Default Severity |
|---------|-------------|------------------|
| `class_prefix` | Class name prefix check | warning |
| `property_naming` | Property naming (lowerCamelCase) | warning |
| `constant_naming` | Constant naming check | warning |
| `method_naming` | Method naming check | warning |
| `line_length` | Line length limit | warning |
| `method_length` | Method length limit | warning |
| `todo_fixme` | TODO/FIXME detection | warning |
| `weak_delegate` | Delegate should use weak | error |
| `block_retain_cycle` | Block retain cycle detection | warning |
| `forbidden_api` | Forbidden API check | error |
| `hardcoded_credentials` | Hardcoded credentials detection | error |

### OCLint Rules

OCLint provides 70+ rules in categories:

- **Basic**: Dead code, null checks, etc.
- **Convention**: Switch/case, loops, etc.
- **Empty**: Empty statement detection
- **Naming**: Naming conventions
- **Redundant**: Redundant code
- **Size**: Cyclomatic complexity, method length, etc.
- **Unused**: Unused code detection

## Custom Rules

### Python Rules (Recommended)

Create a rule file in `custom_rules/python/`:

```python
from core.rule_engine import BaseRule

class MyCustomRule(BaseRule):
    identifier = "my_rule"
    name = "My Custom Rule"
    description = "Check for custom patterns"
    default_severity = "warning"

    def check(self, file_path, content, lines, changed_lines):
        violations = []
        for line_num, line in enumerate(lines, 1):
            if not self.should_check_line(line_num, changed_lines):
                continue
            if "bad_pattern" in line:
                violations.append(self.create_violation(
                    file_path, line_num, 1, "Found bad pattern"
                ))
        return violations
```

### C++ Rules

Create rule files in `custom_rules/cpp/` and rebuild OCLint.

## Command Line Options

```
biliobjclint [options]

Options:
  --config, -c PATH       Configuration file path
  --project-root, -p PATH Project root directory
  --incremental, -i       Incremental check mode
  --base-branch, -b NAME  Base branch for incremental comparison
  --files, -f FILE...     Specific files to check
  --xcode-output, -x      Xcode format output (default)
  --json-output, -j       JSON format output
  --no-oclint             Disable OCLint
  --no-python-rules       Disable Python rules
  --verbose, -v           Verbose output
```

## Project Structure

```
BiliObjCLint/
├── oclint/                   # OCLint source code
├── scripts/
│   ├── biliobjclint.py       # Main entry point
│   ├── claude_fixer.py       # Claude auto-fix module
│   ├── xcode_integrator.py   # Xcode integration
│   ├── core/                 # Core modules
│   │   ├── config.py         # Configuration
│   │   ├── git_diff.py       # Incremental detection
│   │   ├── oclint_runner.py  # OCLint wrapper
│   │   ├── reporter.py       # Output formatting
│   │   ├── rule_engine.py    # Rule engine
│   │   └── logger.py         # Logging
│   ├── rules/                # Built-in rules
│   ├── lib/                  # Shell libraries
│   ├── setup_env.sh          # Environment setup
│   ├── install_xcode.sh      # Xcode installation
│   └── build_oclint.sh       # OCLint build script
├── custom_rules/
│   ├── python/               # Python custom rules
│   └── cpp/                  # C++ custom rules
├── config/
│   └── default.yaml          # Default configuration
├── logs/                     # Log files
└── test/                     # Test files
```

## FAQ

### Q: How to check only specific types of issues?

Configure `.biliobjclint.yaml` to disable unwanted rules:

```yaml
python_rules:
  todo_fixme:
    enabled: false
```

### Q: How to ignore specific files?

Add exclusion patterns in the configuration:

```yaml
excluded:
  - "**/*Generated*.m"
  - "Legacy/**"
```

### Q: OCLint build fails?

Use the Homebrew pre-built version:

```bash
brew install oclint
```

Or use Python rules only:

```bash
biliobjclint --no-oclint
```

### Q: How to use Claude auto-fix?

1. Install [Claude Code CLI](https://claude.ai/code)
2. Configure in `.biliobjclint.yaml`:

```yaml
claude_autofix:
  trigger: "any"
  mode: "silent"
```

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

This project includes OCLint, which is licensed under the BSD 3-Clause License.
